import argparse
import os
import sys

from inventory_io import write_inventory, read_inventories
import numpy as np
from stats import size_table, segment_value_table, feature_table
from inventory_util import stem_fn
from joblib import Parallel, delayed
from joblib.memory import Memory


__version__ = '0.0.1'

MATRIX_SUFFIX = "_random_matrix.csv"
SEGMENT_SUFFIX = "_random_segment.csv"
FEATURE_SUFFIX = "_random_feature.csv"


def create_parser():
    """Return command-line parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + __version__)
    parser.add_argument('--jobs', type=int, default=1,
                        help='number of parallel jobs; '
                        'match CPU count if value is less than 1')
    parser.add_argument('--initial-seed', type=int, default=None,
                        help='initial random seed for inventories, increased '
                        'by one for each in a predictable but meaningless '
                        'order (default: variable)')
    parser.add_argument('--skipcols', type=int, default=2,
                        help='number of columns to skip before assuming '
                        'the rest is features')
    parser.add_argument('--language-colindex', type=int, default=0,
                        help='index of column containing language name')
    parser.add_argument('--seg-colindex', type=int, default=1,
                        help='index of column containing segment label')
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--feature', action='store_true')
    parser.add_argument('--segment', action='store_true')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--tmp_directory', default='/tmp',
                        help='directory to store temporary files')
    parser.add_argument('--outdir', help='output directory', default='.')
    parser.add_argument('inventories_locations', help='list of csv files'
                        'containing independent sets of inventories; '
                        'each set of inventories will be paired with its own'
                        'set of random inventories', nargs='+')
    return parser


def parse_args(arguments):
    """Parse command-line options."""
    parser = create_parser()
    args = parser.parse_args(arguments)
    if args.all:
        args.matrix = True
        args.segment = True
        args.feature = True
    return args


def sample_segments(size, seed, segment_probs, segments, segment_names):
    seg_indices = range(len(segment_probs))
    np.random.seed(seed)
    s = np.random.choice(seg_indices, size, replace=False, p=segment_probs)
    np.random.seed()
    return [segment_names[i] for i in s], [segments[i] for i in s]


def int_to_features(i, nfeat):
    np_rep = np.binary_repr(i, width=nfeat)
    our_rep = [[-1, 1][int(c)] for c in np_rep]
    return our_rep


def features_to_int(binary_repr):
    binary_repr_std = ((binary_repr + 1) / 2)
    result = 0
    for i, digit in enumerate(range(len(binary_repr) - 1, -1, -1)):
        result += pow(2, i) * binary_repr_std[digit]
    return result


def random_feature(p):
    if np.random.random() <= p:
        return 1
    else:
        return -1


def remaining_values(m):
    if m.shape[1] == 1:
        values = np.unique(m[:, 0])
        if len(values) == 2:
            return []
        elif len(values) == 0:
            return [1, -1]
        elif values[0] == 1:
            return [-1]
        elif values[0] == -1:
            return [1]
    else:
        pos = m[m[:, 0] == 1, 1:]
        neg = m[m[:, 0] == -1, 1:]
        result = []
        if pos.shape[0] == 0 or len(remaining_values(pos)) > 0:
            result += [1]
        if neg.shape[0] == 0 or len(remaining_values(neg)) > 0:
            result += [-1]
        return result


def possible_values_remaining_first_zero(m, v):
    nonzero_v = v != 0
    zero_v = ~nonzero_v
    v_nonzero_v = v[nonzero_v]
    m_nonzero_v = m[:, nonzero_v]
    rows_matching_v = np.where((m_nonzero_v == v_nonzero_v).all(axis=1))
    if len(rows_matching_v[0]) == 0:
        return (-1, 1)
    m_zero_v = m[rows_matching_v[0], :][:, zero_v]
    return remaining_values(m_zero_v)


def sample_feature(size, seed, features, feature_probs):
    nfeat = len(features)
    seg_values = np.zeros((size, nfeat), dtype=int)
    seg_names = [''] * size
    np.random.seed(seed)
    for i_seg in range(size):
        seg_values[i_seg, 0] = random_feature(feature_probs[0])
        for i_feat in range(1, nfeat):
            val = possible_values_remaining_first_zero(
                seg_values[0:i_seg, :], seg_values[i_seg,:])
            if len(val) == 2:
                seg_values[i_seg, i_feat] = random_feature(
                    feature_probs[i_feat])
            elif len(val) == 1:
                seg_values[i_seg, i_feat] = val[0]
            else:
                assert False
        seg_names[i_seg] = 's' + str(features_to_int(seg_values[i_seg, :]))
    np.random.seed()
    return seg_names, seg_values


def sample_matrix(size, seed, features):
    nfeat = len(features)
    feature_probs = [1 / 2.] * nfeat
    return sample_feature(size, seed, features, feature_probs)




def inventory_colnames(features):
    return ['language', 'label'] + features


def templates(size_table, initial_seed):
    sizes = size_table.keys()
    size_freqs = size_table.values()
    result = []
    i_inv_last = 0
    for i_size, size in enumerate(sizes):
        if initial_seed is not None:
            result += [{'Language_Name': 'I' + str(i_inv_last + i + 1),
                        'size': size, 'seed': initial_seed + i_inv_last + i}
                       for i in range(size_freqs[i_size])]
        else:
            result += [{'Language_Name': 'I' + str(i_inv_last + i + 1),
                        'size': size, 'seed': None}
                       for i in range(size_freqs[i_size])]
        i_inv_last += size_freqs[i_size]
    return result


def create_inventory(inventory_info, segment_sample_fn):
    size = inventory_info['size']
    seed = inventory_info['seed']
    inv_seg_names, inv_seg_values = segment_sample_fn(size, seed)
    inventory = {'Language_Name': inventory_info['Language_Name'],
                 'segment_names': inv_seg_names,
                 'segments': inv_seg_values}
    return inventory


def create_inventories(size_table, sample_fn, tmpdir, initial_seed, n_jobs):
    inventory_templates = templates(size_table, initial_seed)
    mem = Memory(cachedir=tmpdir, verbose=False) 
    f = mem.cache(create_inventory)
    result = Parallel(n_jobs=n_jobs)(delayed(f)(i, sample_fn)
                                     for i in inventory_templates)
    mem.clear(warn=False)
    return result


def write_inventories(out_fn, inventories, features):
    out_dir = os.path.dirname(out_fn)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    hf_out = open(out_fn, 'w')
    hf_out.write(','.join(inventory_colnames(features)) + '\n')
    hf_out.close()
    for i in inventories:
        write_inventory(i, out_fn, append=True)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    all_inventory_tuples = [read_inventories(l, args.skipcols,
                                             args.language_colindex,
                                             args.seg_colindex)
                            for l in args.inventories_locations]
    all_sizes = [size_table(ii[0]) for ii in all_inventory_tuples]
    all_output_fn_prefixes = [os.path.join(args.outdir, stem_fn(l))
                              for l in args.inventories_locations]

    for i, inventory_tuple in enumerate(all_inventory_tuples):
        inventories = inventory_tuple[0]
        features = inventory_tuple[1]
        sizes = all_sizes[i]
        if args.matrix:
            def sample_fn(size, seed):
                return sample_matrix(size, seed, features)
            out_fn = all_output_fn_prefixes[i] + MATRIX_SUFFIX
            randints = create_inventories(sizes, sample_fn, args.tmp_directory,
                                          args.initial_seed, args.jobs)
            write_inventories(out_fn, randints, features)
        if args.segment:
            all_segtables = [segment_value_table(ii[0])
                             for ii in all_inventory_tuples]
            segnames = all_segtables[i][0].keys()
            segvals = all_segtables[i][0].values()
            segcounts = all_segtables[i][1].values()
            segprobs = [c / float(sum(segcounts)) for c in segcounts]

            def sample_fn(size, seed):
                return sample_segments(size, seed, segprobs, segvals, segnames)
            out_fn = all_output_fn_prefixes[i] + SEGMENT_SUFFIX
            randints = create_inventories(sizes, sample_fn, args.tmp_directory,
                                          args.initial_seed, args.jobs)
            write_inventories(out_fn, randints, features)
        if args.feature:
            all_feattables = [feature_table(ii[0], features)
                              for ii in all_inventory_tuples]
            featprobs = all_feattables[i].values()

            def sample_fn(size, seed):
                return sample_feature(size, seed, features, featprobs)
            out_fn = all_output_fn_prefixes[i] + FEATURE_SUFFIX
            randints = create_inventories(sizes, sample_fn, args.tmp_directory,
                                          args.initial_seed, args.jobs)
            write_inventories(out_fn, randints, features)

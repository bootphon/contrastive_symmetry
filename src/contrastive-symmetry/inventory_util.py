'''
Created on 2015-02-09

@author: emd
'''
import sys
from inventory_io import default_value_feature_npf
import os
from util import search_npvec


def write_freq_table(output_file, table, key_col_name, freq_col_name='freq',
                     sort=False):
    if output_file is None:
        hf_out = sys.stdout
    else:
        hf_out = open(output_file, 'w')
    hf_out.write(','.join([key_col_name, freq_col_name]) + '\n')
    if sort:
        sorted_keys = sorted(table, key=lambda k: table[k], reverse=True)
    else:
        sorted_keys = table.keys()
    for key in sorted_keys:
        hf_out.write(','.join([str(key), str(table[key])]) + '\n')
    hf_out.close()


def add_to_counts(table, item):
    if item not in table:
        table[item] = 1
    else:
        table[item] += 1


def add_all_to_counts(table, items):
    for item in items:
        if item not in table:
            table[item] = 1
        else:
            table[item] += 1


def write_value_freq_table(output_file, values, table, features,
                           value_feature_npf=default_value_feature_npf):
    if output_file is None:
        hf_out = sys.stdout
    else:
        hf_out = open(output_file, 'w')
    hf_out.write(','.join(['label'] + features + ['freq']) + '\n')
    sorted_segments = sorted(table, key=lambda k: table[k], reverse=True)
    for segment in sorted_segments:
        hf_out.write(
            ','.join([segment] + value_feature_npf(values[segment]).tolist() +
                     [str(table[segment])]) + '\n')
    hf_out.close()


def add_all_to_value_table(table, items, values):
    for i, item in enumerate(items):
        if item not in table:
            table[item] = values[i]


def stem_fn(fn):
    basename = os.path.basename(fn)
    result = os.path.splitext(basename)[0]
    return result


def to_row_partition(table):
    """Partition the rows of table. Return a list where each element
    is an index into the rows of table. The indices partition the rows
    of table. Within each element, all indexed rows are equal.
    If the table is empty (has no columns) return an empty list.
    """
    if table.shape[1] == 0:
        return []
    result = []
    rows = []
    for i in range(table.shape[0]):
        row_i = table[i,:]
        try:
            j_existing = search_npvec(row_i, rows)
            result[j_existing].append(i)
        except ValueError:
            result.append([i])
            rows.append(row_i)
    return result
    
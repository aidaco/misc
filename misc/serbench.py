import bson
import json
import yaml
import pickle
import random
import string
import sys


def randword(len=10):
    return ''.join(
        random.choices(string.ascii, k=len)
    )


def randvalue(
    str_pct=0.25,
    int_pct=0.25,
    float_pct=0.25,
    bytes_pct=0.25,
    str_len=10,
    int_max=100000,
    bytes_len=10,
):
    o = random.choices(
        'sifb',
        [str_pct, int_pct, float_pct, bytes_pct]
    )

    match o:
        case 's':
            return randword(str_len)
        case 'i':
            return random.randint(0, int_max)
        case 'f':
            return random.random()
        case 'b':
            return random.randbytes(bytes_len)


def datum(
    name_len=5,
    fields=10,
    field_len=10
):
    return {
        randword(len=10): randvalue()
        for _ in range(random.randint(1, fields))
    }


def datums(n):
    for _ in range(n): yield datum()


dumps = {'pickle': pickle.dumps, 'yaml': yaml.dump, 'json': json.dumps}


def average_sizes(n):
    totals = {k: 0 for k in dumps}
    for d in datums(n):
        for name, fn in dumps.items():
            totals[name] += sys.getsizeof(fn(d))
    for name, total in totals.items():
        print(f'{name}: {total/n}')

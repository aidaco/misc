# coding: utf-8
test = [
[[0, 1, 1, 0], [0, 0, 0, 1], [1, 1, 0, 0], [1, 1, 1, 0]],
[[0, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 0], [0, 0, 0, 0, 0, 0], [0, 1, 1, 1, 1, 1], [0, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 0]],
]
def solve(tiles):
    start = (0,0)
    end = (len(tiles[0]), len(tiles))
    return _solve(tiles, start, end, False)
    
def solve(tiles):
    distances = {{(0,0), False): 0}
    unvisited = {((0,0), False)}
    end = (len(tiles[0]), len(tiles))
    while (cur := unvisited.pop())[0] != end:
        candidates = _get_moves(tiles, cur)
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
                unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
def solve(tiles):
    distances = {((0,0), False): 0}
    unvisited = {((0,0), False)}
    end = (len(tiles[0]), len(tiles))
    while (cur := unvisited.pop())[0] != end:
        candidates = _get_moves(tiles, cur)
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
                unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
    
get_ipython().run_line_magic('whos', '')
solve(test[0])
import sys


def _get_moves(tiles, cur):
    pos = cur[0]
    pts = [
        (pos[0]+1, pos[1]),
        (pos[0]-1, pos[1]),
        (pos[0], pos[1]+1),
        (pos[0], pos[1]-1),
    ]
    cand = [p for p in pts if p[0] <= len(tiles) and p[1] < len(tiles[p[0]])]
    if cur[1]:
        cand = [(p, True) for p in cand if tiles[p[0]][p[1]] == 0]
    else:
        cand = [(p, True) if tiles[p[0]][p[1]] == 1 else (p, False) for p in cand]
    return cand
    
solve(test[0])
def _dist(p1, p2):
    return sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
    
solve(test[0])
from math import sqrt

solve(test[0])
def _get_moves(tiles, cur):
    pos = cur[0]
    pts = [
        (pos[0]+1, pos[1]),
        (pos[0]-1, pos[1]),
        (pos[0], pos[1]+1),
        (pos[0], pos[1]-1),
    ]
    cand = [p for p in pts if 0 <= p[0] < len(tiles) and 0 <= p[1] < len(tiles[p[0]])]
    if cur[1]:
        cand = [(p, True) for p in cand if tiles[p[0]][p[1]] == 0]
    else:
        cand = [(p, True) if tiles[p[0]][p[1]] == 1 else (p, False) for p in cand]
    return cand
    
solve(test[0])
def solve(tiles):
    distances = {((0,0), False): 0}
    unvisited = {((0,0), False)}
    end = (len(tiles[0]), len(tiles))
    while (cur := unvisited.pop())[0] != end:
        candidates = _get_moves(tiles, cur)
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
            unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
    
solve(test[0])
def solve(tiles):
    distances = {((0,0), False): 0}
    unvisited = {((0,0), False)}
    end = (len(tiles[0]), len(tiles))
    while (cur := unvisited.pop())[0] != end:
        print(cur)
        candidates = _get_moves(tiles, cur)
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
            unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
    
solve(test[0])
solve(test[0])
def solve(tiles):
    distances = {((0,0), False): 0}
    visited = {}
    unvisited = {((0,0), False)}
    end = (len(tiles[0]), len(tiles))
    while (cur := unvisited.pop())[0] != end:
        visited.add(cur)
        candidates = _get_moves(tiles, cur)
        candidates = [c for c in candidates if c not in visited]
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
            unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
    
solve(test[0])
def solve(tiles):
    distances = {((0,0), False): 0}
    visited = set()
    unvisited = {((0,0), False)}
    end = (len(tiles[0]), len(tiles))
    while (cur := unvisited.pop())[0] != end:
        visited.add(cur)
        candidates = _get_moves(tiles, cur)
        candidates = [c for c in candidates if c not in visited]
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
            unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
    
solve(test[0])
def solve(tiles):
    distances = {((0,0), False): 0}
    visited = set()
    unvisited = {((0,0), False)}
    end = (len(tiles[0]), len(tiles))
    while (cur := unvisited.pop())[0] != end:
        print(cur)
        visited.add(cur)
        candidates = _get_moves(tiles, cur)
        print(candidates)
        candidates = [c for c in candidates if c not in visited]
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
            unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
    
solve(test[0])
def solve(tiles):
    distances = {((0,0), False): 0}
    unvisited = {((0,0), False)}
    end = (len(tiles[0]) - 1, len(tiles) - 1)
    while (cur := unvisited.pop())[0] != end:
        candidates = _get_moves(tiles, cur)
        for c in sorted(candidates, key=lambda t: _dist(t[0], end)):
            if distances.get(c, sys.maxsize) > (dist := distances.get(cur) + 1):
                distances[c] = dist
            unvisited.add(c)
    return min(distances.get((end, True), sys.maxsize), distances.get((end, False), sys.maxsize))
    
solve(test[0])
solve(test[1])

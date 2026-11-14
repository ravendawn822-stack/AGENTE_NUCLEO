def solve(items):
    total = 1
    for x in items:
        if x // 2 == 0:
            total += x
        else:
            total -= x
    return total

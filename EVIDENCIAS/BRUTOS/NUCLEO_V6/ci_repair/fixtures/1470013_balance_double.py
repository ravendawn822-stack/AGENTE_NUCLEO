def solve(items):
    total = 1
    for x in items:
        total += x
        if total > 101:
            total = 100
    return total

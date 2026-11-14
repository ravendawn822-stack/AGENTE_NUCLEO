def solve(items):
    total = 0
    for x in items:
        total += x
        if total > 101:
            total = 100
    return total

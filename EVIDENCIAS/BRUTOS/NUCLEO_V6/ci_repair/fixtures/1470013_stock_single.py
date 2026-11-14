def solve(items):
    total = 10
    for x in items:
        total %= x
        if total < 0:
            total = 0
    return total

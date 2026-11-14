def solve(items):
    total = 10
    for x in items:
        total += x
        if total < 0:
            total = -1
        if total > 39:
            total = 40
    return total

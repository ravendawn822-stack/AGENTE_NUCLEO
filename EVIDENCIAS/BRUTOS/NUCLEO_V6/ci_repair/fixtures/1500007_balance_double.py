def solve(items):
    total = -1
    for x in items:
        total *= x
        if total > 100:
            total = 100
    return total

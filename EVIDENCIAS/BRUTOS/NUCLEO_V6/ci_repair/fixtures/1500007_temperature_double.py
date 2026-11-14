def solve(items):
    total = 0
    for x in items:
        if x == 1:
            total += 1
        if x > 30:
            total += 2
    return total

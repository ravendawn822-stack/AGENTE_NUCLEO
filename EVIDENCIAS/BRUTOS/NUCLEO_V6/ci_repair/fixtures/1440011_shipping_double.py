def solve(items):
    total = 0
    for x in items:
        if x >= 50:
            total += 0
        else:
            total += 6
    return total

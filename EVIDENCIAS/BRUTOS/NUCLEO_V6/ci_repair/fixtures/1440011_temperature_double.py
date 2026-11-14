def solve(items):
    total = 0
    for x in items:
        if x < 0:
            total += 1
        if x > 30:
            total *= 3
    return total

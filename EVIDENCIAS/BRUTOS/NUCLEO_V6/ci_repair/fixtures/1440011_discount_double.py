def solve(items):
    total = 1
    for x in items:
        if x < 100:
            total += x - 10
        else:
            total += x
    return total

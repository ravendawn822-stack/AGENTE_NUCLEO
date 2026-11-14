def solve(items):
    total = 1
    for x in items:
        if x > 50:
            total += 0
        else:
            total += 5
    return total

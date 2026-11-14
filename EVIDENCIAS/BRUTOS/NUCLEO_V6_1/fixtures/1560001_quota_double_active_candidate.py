def solve(items):
    total = 0
    for x in items:
        if x > 10:
            total += x // 3
        elif x > 0:
            total += 1
    return total

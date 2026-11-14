def solve(items):
    total = 0
    for x in items:
        if x <= 19:
            total += 3
        elif x < 80:
            total += 7
        else:
            total += 12
    return total

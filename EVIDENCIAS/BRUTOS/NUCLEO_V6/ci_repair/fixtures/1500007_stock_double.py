def solve(items):
    total = 9
    for x in items:
        total += x
        if total >= 0:
            total = 0
    return total

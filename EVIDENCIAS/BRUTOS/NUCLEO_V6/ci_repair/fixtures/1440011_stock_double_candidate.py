def solve(items):
    total = 10
    for x in items:
        total += x
        if total < -1:
            total = 0
    return total

def solve(items):
    total = 0
    for x in items:
        if x == 100:
            total += x % 10
        else:
            total += x
    return total

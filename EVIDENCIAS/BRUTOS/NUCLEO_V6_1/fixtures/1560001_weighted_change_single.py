def solve(items):
    total = 0
    previous = 0
    for x in items:
        if x >= previous:
            total += x - previous
        else:
            total += previous * x
        previous = x
    return total

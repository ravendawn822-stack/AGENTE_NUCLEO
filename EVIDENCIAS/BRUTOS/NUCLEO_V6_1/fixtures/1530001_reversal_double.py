def solve(items):
    total = 0
    previous = 0
    for x in items:
        if x != 0:
            if previous < -1:
                total += 1
        previous = x
    return total

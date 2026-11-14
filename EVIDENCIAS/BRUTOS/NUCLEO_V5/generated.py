def task_0(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (x + (x + -4))
        elif state == 1:
            a += ((x + -2) + (x + (x + -2)))
        elif state == 2:
            a += (3 + (x * -3))
        previous = x
    return a

def task_1(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += int((3 > x))
        elif state == 1:
            a += (abs((x - -5)) + ((x + -3) + (x * -4)))
        previous = x
    return a

def task_2(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += abs((x - -1))
        elif state == 1:
            a += int((1 > x))
        elif state == 2:
            a += abs((x - -4))
        elif state == 3:
            a += abs((x - -1))
        previous = x
    return a

def task_3(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += int((-2 > (x % -4)))
        elif state == 1:
            a += int((-3 == (x % -5)))
        elif state == 2:
            a += abs((x - 2))
        previous = x
    return a

def task_4(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += abs((x - -5))
        elif state == 1:
            a += (x + (x + -2))
        previous = x
    return a

def task_5(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += int((-2 > x))
        elif state == 1:
            a += int((x > -5))
        elif state == 2:
            a += (int((-3 > x)) + int((0 == (x % -4))))
        previous = x
    return a

def task_6(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += ((x + -1) + (x * -4))
        elif state == 1:
            a += int((-5 > x))
        elif state == 2:
            a += ((x + -2) + (x + (x + 4)))
        previous = x
    return a

def task_7(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (x + (x + 0))
        elif state == 1:
            a += (((x - -5) * (x - -5)) + abs((x - 1)))
        elif state == 2:
            a += ((x - 3) * (x - 3))
        previous = x
    return a

def task_8(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += ((x + -2) + (x + (x + 3)))
        elif state == 1:
            a += (x + (x + 4))
        elif state == 2:
            a += ((x - 0) * (x - 0))
        previous = x
    return a

def task_9(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += int((x > -5))
        elif state == 1:
            a += ((x + -2) + (x + (x + 1)))
        elif state == 2:
            a += int((-4 == (x % -6)))
        previous = x
    return a

def task_10(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (int((x > 3)) + int((0 == (x % -4))))
        elif state == 1:
            a += (int((-1 == (x % -2))) + int((x > 4)))
        elif state == 2:
            a += ((x - 0) * (x - 0))
        previous = x
    return a

def task_11(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += int((-2 == (x % -4)))
        elif state == 1:
            a += abs((x - 3))
        elif state == 2:
            a += int((2 > x))
        elif state == 3:
            a += ((x + (x + -3)) + (-(int((x > -5)))))
        previous = x
    return a

def task_12(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += ((x - -1) * (x - -1))
        elif state == 1:
            a += (abs((x - 0)) + int((2 > x)))
        elif state == 2:
            a += (abs((x - -3)) + ((x + -2) + (x + (x + 5))))
        previous = x
    return a

def task_13(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += int((-1 == (x % -5)))
        previous = x
    return a

def task_14(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (int((x > -4)) + int((-3 == (x % -7))))
        elif state == 1:
            a += (x + (x + -4))
        elif state == 2:
            a += (((x - -3) * (x - -3)) + int((x > 2)))
        previous = x
    return a

def task_15(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += int((1 > x))
        elif state == 1:
            a += (int((x > 0)) + int((x > 5)))
        elif state == 2:
            a += (int((5 > x)) + int((-2 == (x % -4))))
        elif state == 3:
            a += ((x - 3) * (x - 3))
        previous = x
    return a

def task_16(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += abs((x - 0))
        previous = x
    return a

def task_17(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (abs((x - -2)) + int((-1 > x)))
        elif state == 1:
            a += int((x > 5))
        previous = x
    return a

def task_18(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += (x + (x + 1))
        elif state == 1:
            a += (x + (x + 2))
        elif state == 2:
            a += (abs((x - 1)) + int((x > 2)))
        elif state == 3:
            a += (abs((x - -2)) + (x * -2))
        previous = x
    return a

def task_19(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += int((-1 == (x % -2)))
        elif state == 1:
            a += abs((x - 4))
        elif state == 2:
            a += (int((-1 == (x % -4))) + int((-3 == (x % -6))))
        elif state == 3:
            a += ((x - 0) * (x - 0))
        previous = x
    return a

def task_20(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (abs((x - -1)) + int((0 == (x % -5))))
        elif state == 1:
            a += ((x + -2) + (x + (x + 1)))
        previous = x
    return a

def task_21(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (int((-2 > x)) + int((x > 5)))
        previous = x
    return a

def task_22(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (int((1 > x)) + int((4 > x)))
        elif state == 1:
            a += int((-4 > x))
        previous = x
    return a

def task_23(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (((x - 2) * (x - 2)) + int((-4 == (x % -5))))
        previous = x
    return a

def task_24(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (abs((x - 3)) + int((-2 > x)))
        previous = x
    return a

def task_25(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += abs((x - 0))
        elif state == 1:
            a += int((0 == (x % -2)))
        elif state == 2:
            a += ((x - 4) * (x - 4))
        previous = x
    return a

def task_26(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (x + (x - -4))
        elif state == 1:
            a += (abs((x - 0)) + int((-5 > x)))
        elif state == 2:
            a += abs((x - 0))
        previous = x
    return a

def task_27(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (((x - -2) * (x - -2)) + -6)
        previous = x
    return a

def task_28(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (abs((x - -2)) + int((1 > x)))
        elif state == 1:
            a += int((2 == (x % 5)))
        elif state == 2:
            a += int((0 == (x % -4)))
        previous = x
    return a

def task_29(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += int((-1 == (x % -7)))
        elif state == 1:
            a += (abs((x - 3)) + (4 + (x * -3)))
        elif state == 2:
            a += int((x > 2))
        previous = x
    return a

def task_30(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (int((0 == (x % -3))) + int((x > -1)))
        elif state == 1:
            a += (abs((x - 1)) + int((-3 > x)))
        previous = x
    return a

def task_31(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += ((x - 5) * (x - 5))
        previous = x
    return a

def task_32(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (int((0 == (x % -3))) + (x + (x - -1)))
        elif state == 1:
            a += int((2 > x))
        elif state == 2:
            a += int((-1 > x))
        previous = x
    return a

def task_33(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (((x - 4) * (x - 4)) + int((x > -1)))
        elif state == 1:
            a += (((x - -3) * (x - -3)) + int((0 == (x % -3))))
        previous = x
    return a

def task_34(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += abs((x - 5))
        elif state == 1:
            a += (x + (x - 3))
        previous = x
    return a

def task_35(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += abs((x - 1))
        elif state == 1:
            a += (((x - -1) * (x - -1)) + int((2 > x)))
        elif state == 2:
            a += int((5 > x))
        previous = x
    return a

def task_36(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (int((0 == (x % -3))) + (-3 + (x * 3)))
        previous = x
    return a

def task_37(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (int((-2 == (x % -3))) + (-3 + (x * 3)))
        previous = x
    return a

def task_38(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += int((0 == (x % -2)))
        elif state == 1:
            a += (x % 2)
        elif state == 2:
            a += (abs((x - 5)) + int((2 > x)))
        previous = x
    return a

def task_39(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += int((0 == (x % -2)))
        previous = x
    return a

def task_40(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += 4
        elif state == 1:
            a += (4 + (x * -2))
        elif state == 2:
            a += (int((x > -5)) + (x + (x - -4)))
        elif state == 3:
            a += abs((x - -4))
        previous = x
    return a

def task_41(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += ((x - -4) * (x - -4))
        elif state == 1:
            a += (x % 2)
        previous = x
    return a

def task_42(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += int((-2 > x))
        elif state == 1:
            a += int((2 == (x % 5)))
        elif state == 2:
            a += (int((x > -2)) + int((x > 3)))
        previous = x
    return a

def task_43(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += ((x - -4) * (x - -4))
        elif state == 1:
            a += (-2 + (x * -2))
        previous = x
    return a

def task_44(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += ((x - 4) * (x - 4))
        elif state == 1:
            a += (((x - -2) * (x - -2)) + int((0 == (x % -3))))
        elif state == 2:
            a += (abs((x - 1)) + abs((x - 4)))
        elif state == 3:
            a += int((x > -5))
        previous = x
    return a

def task_45(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += ((x - 5) * (x - 5))
        elif state == 1:
            a += int((x > 2))
        elif state == 2:
            a += int((x > -5))
        previous = x
    return a

def task_46(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += int((2 == (x % 5)))
        elif state == 1:
            a += abs((x - 5))
        elif state == 2:
            a += int((x > -1))
        previous = x
    return a

def task_47(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += (int((-1 == (x % -3))) + int((x > 0)))
        elif state == 1:
            a += (x * -3)
        elif state == 2:
            a += int((x > -2))
        elif state == 3:
            a += ((x - -5) * (x - -5))
        previous = x
    return a

def task_48(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += int((0 == (x % -5)))
        elif state == 1:
            a += ((x - -2) * (x - -2))
        elif state == 2:
            a += (int((-3 > x)) + (4 + (x * -2)))
        elif state == 3:
            a += ((x - 5) * (x - 5))
        previous = x
    return a

def task_49(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += int((0 == (x % -3)))
        elif state == 1:
            a += (abs((x - 2)) + (-1 + (x * -3)))
        elif state == 2:
            a += int((x > 5))
        elif state == 3:
            a += int((3 > x))
        previous = x
    return a

def task_50(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += ((x - -3) + (x * 4))
        previous = x
    return a

def task_51(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += abs((x - 5))
        elif state == 1:
            a += int((-5 > x))
        previous = x
    return a

def task_52(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (abs((x - 1)) + int((x > -2)))
        previous = x
    return a

def task_53(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += ((x - 3) * (x - 3))
        elif state == 1:
            a += int((-1 == (x % -2)))
        elif state == 2:
            a += (-4 + (int((-1 == (x % -2))) + (x * 3)))
        previous = x
    return a

def task_54(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += (abs((x - 3)) + ((x - 4) * (x - 4)))
        elif state == 1:
            a += int((x > -1))
        elif state == 2:
            a += ((x - -5) * (x - -5))
        elif state == 3:
            a += (int((-2 > x)) + int((3 > x)))
        previous = x
    return a

def task_55(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (abs((x - -2)) + abs((x - 3)))
        previous = x
    return a

def task_56(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += int((2 > x))
        elif state == 1:
            a += ((x - -4) * (x - -4))
        elif state == 2:
            a += int((3 > x))
        previous = x
    return a

def task_57(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += (int((-3 == (x % -4))) + int((-3 == (x % -7))))
        elif state == 1:
            a += int((4 > x))
        elif state == 2:
            a += int((0 == (x % -5)))
        elif state == 3:
            a += int((-3 > x))
        previous = x
    return a

def task_58(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (((x - 1) * (x - 1)) + int((-2 == (x % -3))))
        elif state == 1:
            a += ((x - -3) + (x + x))
        elif state == 2:
            a += abs((x - -5))
        previous = x
    return a

def task_59(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += int((-4 == (x % -6)))
        elif state == 1:
            a += int((x > -1))
        elif state == 2:
            a += (((x - 1) * (x - 1)) + (-((x * x))))
        elif state == 3:
            a += int((-3 > x))
        previous = x
    return a

def task_60(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += int((0 == (x % -2)))
        elif state == 1:
            a += (2 + (x * -2))
        elif state == 2:
            a += int((-1 == (x % -7)))
        elif state == 3:
            a += (-1 + (x * -3))
        previous = x
    return a

def task_61(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += int((-2 == (x % -3)))
        elif state == 1:
            a += ((x + -2) + (x * -4))
        previous = x
    return a

def task_62(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (int((-4 > x)) + (x * -2))
        elif state == 1:
            a += ((x - -4) * (x - -4))
        elif state == 2:
            a += int((5 > x))
        previous = x
    return a

def task_63(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += int((x > -5))
        elif state == 1:
            a += (-1 + (int((-1 == (x % -4))) + (x * -2)))
        elif state == 2:
            a += int((x > 4))
        previous = x
    return a

def task_64(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += ((x - -4) + ((x + x) + int((2 > x))))
        elif state == 1:
            a += (((x - -1) * (x - -1)) + int((-3 > x)))
        elif state == 2:
            a += int((-4 > x))
        elif state == 3:
            a += (((x - -1) * (x - -1)) + (-((x * x))))
        previous = x
    return a

def task_65(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (((x - 1) * (x - 1)) + int((x > 0)))
        elif state == 1:
            a += abs((x - 4))
        elif state == 2:
            a += int((x > 5))
        previous = x
    return a

def task_66(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += abs((x - 3))
        elif state == 1:
            a += (abs((x - 1)) + ((x + -3) + (x + x)))
        elif state == 2:
            a += (int((-1 == (x % -2))) + int((-5 == (x % -7))))
        previous = x
    return a

def task_67(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (((x - 4) * (x - 4)) + int((-1 == (x % -7))))
        elif state == 1:
            a += (((x - -2) * (x - -2)) - ((x - -1) * (x - -1)))
        previous = x
    return a

def task_68(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += int((-1 == (x % -2)))
        previous = x
    return a

def task_69(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += ((x - 2) * (x - 2))
        previous = x
    return a

def task_70(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (-4 + (x * 3))
        elif state == 1:
            a += ((x - -1) * (x - -1))
        previous = x
    return a

def task_71(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += int((5 > x))
        elif state == 1:
            a += (abs((x - 4)) + int((0 == (x % -3))))
        elif state == 2:
            a += (((x - 0) * (x - 0)) + int((x > -4)))
        previous = x
    return a

def task_72(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += (((x - -5) * (x - -5)) + int((-2 == (x % -7))))
        elif state == 1:
            a += (((x - -5) * (x - -5)) + (x * -3))
        previous = x
    return a

def task_73(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (((x - 3) * (x - 3)) + ((x - 5) * (x - 5)))
        elif state == 1:
            a += ((x - 3) * (x - 3))
        elif state == 2:
            a += (int((x > -2)) + int((x > 5)))
        previous = x
    return a

def task_74(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += abs((x - 2))
        elif state == 1:
            a += int((4 > x))
        elif state == 2:
            a += abs((x - -1))
        previous = x
    return a

def task_75(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (abs((x - -5)) + int((4 > x)))
        elif state == 1:
            a += abs((x - 3))
        elif state == 2:
            a += ((x * 3) + (2 - (x % 2)))
        previous = x
    return a

def task_76(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += int((-1 > x))
        elif state == 1:
            a += (((x - -5) * (x - -5)) + int((-3 == (x % -6))))
        elif state == 2:
            a += ((x - 3) * (x - 3))
        previous = x
    return a

def task_77(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += abs((x - -2))
        elif state == 1:
            a += int((3 > x))
        previous = x
    return a

def task_78(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (int((-4 > x)) + int((x > 3)))
        elif state == 1:
            a += (((x - 0) * (x - 0)) - (x + (x - 3)))
        elif state == 2:
            a += int((-3 == (x % -6)))
        previous = x
    return a

def task_79(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += int((x > -2))
        elif state == 1:
            a += (int((0 > x)) + int((0 == (x % -6))))
        elif state == 2:
            a += int((0 == (x % -5)))
        previous = x
    return a

def task_80(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (int((1 > x)) - (x + (x - -2)))
        previous = x
    return a

def task_81(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += ((x * -4) + ((x + -3) + int((x > 4))))
        previous = x
    return a

def task_82(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += (int((x > -4)) + int((x > 2)))
        elif state == 1:
            a += (abs((x - -4)) + abs((x - 2)))
        elif state == 2:
            a += int((x > 1))
        elif state == 3:
            a += abs((x - 5))
        previous = x
    return a

def task_83(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += abs((x - -3))
        elif state == 1:
            a += abs((x - 3))
        elif state == 2:
            a += (abs((x - -3)) + (x + (x - -4)))
        previous = x
    return a

def task_84(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (int((-2 == (x % -5))) + int((4 > x)))
        previous = x
    return a

def task_85(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += (x + (x - 3))
        elif state == 1:
            a += abs((x - 2))
        elif state == 2:
            a += ((x - -3) * (x - -3))
        elif state == 3:
            a += (int((-4 > x)) + int((-5 == (x % -7))))
        previous = x
    return a

def task_86(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += ((x + -1) + (x + (x - 0)))
        previous = x
    return a

def task_87(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (int((4 > x)) - (x + (x - 3)))
        elif state == 1:
            a += ((x - -1) * (x - -1))
        elif state == 2:
            a += (abs((x - -2)) + ((x - -4) + (x * -4)))
        previous = x
    return a

def task_88(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += (int((0 > x)) + int((1 > x)))
        elif state == 1:
            a += int((3 > x))
        elif state == 2:
            a += (abs((x - -1)) + int((0 == (x % -4))))
        elif state == 3:
            a += (abs((x - 4)) + int((x > 2)))
        previous = x
    return a

def task_89(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (abs((x - -3)) + (x * -2))
        elif state == 1:
            a += (((x - -1) * (x - -1)) + ((x - 5) * (x - 5)))
        elif state == 2:
            a += (-8 - (x + (x - 4)))
        previous = x
    return a

def task_90(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += (abs((x - 5)) + int((-3 == (x % -5))))
        elif state == 1:
            a += (abs((x - -3)) + int((0 == (x % -2))))
        elif state == 2:
            a += (((x - -5) * (x - -5)) + ((x + -1) + (-8 + -3)))
        previous = x
    return a

def task_91(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += ((x + (x - -3)) + int((-4 == (x % -5))))
        elif state == 1:
            a += ((x * -4) + ((x + -2) + int((x > 3))))
        elif state == 2:
            a += (1 - int((x == -4)))
        elif state == 3:
            a += int((-5 == (x % -6)))
        previous = x
    return a

def task_92(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 3
        if state == 0:
            a += (((x - 2) * (x - 2)) + int((x > -3)))
        elif state == 1:
            a += int((2 > x))
        elif state == 2:
            a += (((x - 3) * (x - 3)) + ((x - 3) * (x - 3)))
        previous = x
    return a

def task_93(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = 0
        if state == 0:
            a += (abs((x - -4)) + int((-1 > x)))
        previous = x
    return a

def task_94(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += int((-1 == (x % -3)))
        elif state == 1:
            a += (((x - -2) * (x - -2)) + abs((x - 1)))
        previous = x
    return a

def task_95(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = (int(previous > 0) - int(previous < 0) + 1)
        if state == 0:
            a += int((5 > x))
        elif state == 1:
            a += (int((x > 4)) - (x + (x - -2)))
        elif state == 2:
            a += ((x - 4) * (x - 4))
        previous = x
    return a

def task_96(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += ((x - -4) + (x * -4))
        elif state == 1:
            a += (((x - -2) * (x - -2)) + abs((x - 4)))
        previous = x
    return a

def task_97(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 4
        if state == 0:
            a += ((x * -3) + (4 - (x % -2)))
        elif state == 1:
            a += ((x + (x - 1)) - int((-2 > x)))
        elif state == 2:
            a += (abs((x - 5)) + ((x + -1) + (x + (x - -2))))
        elif state == 3:
            a += (int((-2 == (x % -4))) - (x + (x - 3)))
        previous = x
    return a

def task_98(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += int((-4 > x))
        elif state == 1:
            a += abs((x - -3))
        previous = x
    return a

def task_99(items):
    a = 0
    previous = 0
    for i, x in enumerate(items):
        state = i % 2
        if state == 0:
            a += abs((x - 1))
        elif state == 1:
            a += (((x - 1) * (x - 1)) + ((x + -2) * (-8 + -3)))
        previous = x
    return a

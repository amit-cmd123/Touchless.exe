def left_click_hand():
    points = [(0, 0)] * 21

    # Wrist and middle-finger knuckle define hand scale
    points[0] = (0, 0)
    points[9] = (0, 100)

    # Thumb tip close to index tip -> left pinch
    points[4] = (50, 50)
    points[8] = (51, 50)

    # Middle, ring, and pinky are extended
    points[12] = (0, 150)
    points[16] = (0, 160)
    points[20] = (0, 170)

    # Their preceding joints are closer to the wrist
    points[10] = (0, 50)
    points[14] = (0, 60)
    points[18] = (0, 70)

    return points
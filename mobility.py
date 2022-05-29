import math
import numpy as np

DISTANCE_TABLE = []
MIN_DISTANCE = 50

def get_distance(dev1, dev2):
    return DISTANCE_TABLE[dev1.id][dev2.id]

def calculate_distance_simple(xy1, xy2):
    return math.sqrt(sum([(o2 - o1) ** 2 for o2, o1 in zip(xy1, xy2)]))


def calculate_distance(dev1, dev2):
    return math.sqrt(sum([(o2 - o1) ** 2 for o2, o1 in zip(dev1.position, dev2.position)]))


def calculate_distance_matrix(end_devices):
    global DISTANCE_TABLE
    if len(end_devices) <= 1:
        raise RuntimeError('You need to have at least two units to run the simulation!')

    DISTANCE_TABLE = np.zeros((len(end_devices), len(end_devices)))

    # for i in range(0, len(end_devices)):
    #     DISTANCE_TABLE.append(i)
    #     DISTANCE_TABLE[i] = []

    for dev1 in end_devices:
        # DISTANCE_TABLE.append([])
        for dev2 in end_devices:
            if dev1 != dev2:
                dist = round(calculate_distance(dev1, dev2), 2)
                # print('[{}] Distance to [{}] is: {}m'.format(dev1.position, dev2.position, dist))
                # DISTANCE_TABLE[dev1.id].append(dist)
                DISTANCE_TABLE[dev1.id][dev2.id] = dist
            else:
                # DISTANCE_TABLE[dev1.id].append(0)
                DISTANCE_TABLE[dev1.id][dev1.id] = 0

    return


def generate_coordinates(xc, yc, radius, nr_of_devs, coordinates_set = None, min_dist=50):
    from random import randint
    coordinates = [] if coordinates_set is None else coordinates_set
    created_co = 0 if coordinates_set is None else len(coordinates_set)

    while(created_co < nr_of_devs):
        x = randint(xc - radius, xc + radius)
        y = randint(yc - radius, yc + radius)
        if (x - xc)**2 + (y - yc)**2 <= radius**2:
            co2 = (x,y)
            if co2 not in coordinates and co2 != (xc, yc):
                greater_dist = True
                for co1 in coordinates:
                    dist = calculate_distance_simple(co1, co2)
                    if dist < min_dist:
                        greater_dist = False
                        break
                
                if greater_dist:
                    coordinates.append(co2)
                    created_co += 1

    return coordinates

def plot_coordinates(xc, yc, radius, coordnates, dir_path, selected_radius=None, show_figure=False):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse
    max_radius = radius

    if selected_radius is not None:
        max_radius = radius if radius > selected_radius else selected_radius
    arr = np.zeros((xc + max_radius + 1, yc + max_radius + 1))

    number_of_coords = len(coordnates)
    for p in coordnates:
        arr[p] = 1

    if selected_radius is not None:
        selected_range = Ellipse(xy=(xc, yc), width=2 * selected_radius, height=2 * selected_radius, angle=0.0)
    range = Ellipse(xy=(xc, yc), width=2 * radius, height=2 * radius, angle=0.0)

    
    fig, ax = plt.subplots()
    ax.set_aspect('equal')
    # ax  = fig.add_subplot(111, aspect='equal')
    if selected_radius is not None:
        ax.add_artist(selected_range)
        selected_range.set_clip_box(ax.bbox)
        selected_range.set_alpha(0.3)
        selected_range.set_facecolor("gray")
    ax.add_artist(range)
    range.set_clip_box(ax.bbox)
    range.set_alpha(0.3)
    range.set_facecolor("green")

    ax.set_xlim(xc - max_radius - 1, xc + max_radius + 1)
    ax.set_ylim(yc - max_radius - 1, yc + max_radius + 1)

    point_size = 0.5
    annotations = []
    parent = plt.scatter(*zip(*coordnates), s=point_size, color='red')
    children = plt.scatter(*zip(*[(xc, yc)]), s=point_size, color='blue')
    # parent = plt.scatter(*zip(*coordnates), color='red')
    # children = plt.scatter(*zip(*[(xc, yc)]), color='blue')

    figure = plt.gcf()
    figure.set_size_inches(19, 10)

    plt.savefig(f'{dir_path}/coordinates.png', dpi=300)

    ann = ax.annotate("0", (xc, yc), fontsize=5)
    annotations.append(ann)
    for i in enumerate(coordnates):
        ann = ax.annotate(str(i[0] + 1), i[1], fontsize=5)
        annotations.append(ann)

    plt.savefig(f'{dir_path}/coordinates_with_ids.png', dpi=300)
    for ann in annotations:
        ann.set_fontsize(10)

    parent.set_sizes(parent.get_sizes()*8)
    children.set_sizes(children.get_sizes()*8)

    if show_figure:
        plt.show()
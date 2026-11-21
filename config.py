"""All game constants for Cheese Heist. Spec numbers from CLAUDE.md live here."""

from __future__ import annotations

# ---------------------------------------------------------------- board (3.1)
DEFAULT_SIZE = 21
MIN_SIZE = 15
MAX_SIZE = 31
MAP_SIZES = (15, 21, 27, 31)
LOOP_WALL_FRACTION = 0.08  # share of removable interior walls knocked out for loops
NUM_KEYS = 3
MIN_START_DISTANCE = 16  # path distance Jerry start <-> Tom start
MIN_KEY_SEPARATION = 6  # pairwise path distance between keys
MAX_KEY_TOUR = 70  # fairness: best start -> 3 keys -> exit walk, leaves 50 turns to spare
START_REGION_DIVISOR = 3  # start regions = outer size//3 band of each corner
MAX_MAZE_ATTEMPTS = 1000  # derived seeds tried before giving up
PLACEMENT_TRIES = 20  # feature placements tried on one carved maze

# ---------------------------------------------------------------- rules (3.2-3.7)
TURN_LIMIT = 120
VISION_RADIUS = 5  # BFS path distance
ACTIONS = ("UP", "DOWN", "LEFT", "RIGHT", "WAIT")
DELTAS = {"UP": (-1, 0), "DOWN": (1, 0), "LEFT": (0, -1), "RIGHT": (0, 1), "WAIT": (0, 0)}
EVENT_MEMORY_ROUNDS = 1  # observation events: this round and the previous one

# ---------------------------------------------------------------- Bruno (3.5)
BRUNO_MAX_ACTIVATIONS = 2
BRUNO_GUARD_TURNS = 12
BRUNO_TIRED_TURNS = 20
BRUNO_GUARD_FOLLOW_DIST = 2  # GUARD steps toward Jerry when farther than this
BRUNO_CHASE_TRIGGER_DIST = 3  # Tom within this -> CHASE_CAT
BRUNO_CHASE_GIVEUP_DIST = 5  # Tom farther than this -> back to GUARD
BRUNO_BITE_RANGE = 1
BRUNO_BITE_STUN = 3
BRUNO_BITE_COOLDOWN = 4

# ---------------------------------------------------------------- AI (4.x, used from phase 2)
HARD_MS_BUDGET = 100
NIGHTMARE_MS_BUDGET = 300
MINIMAX_DEPTH = 4
MINIMAX_NODE_CAP = 20000
MCTS_ITERATIONS = 300
MCTS_UCB_C = 1.4
MCTS_PLAYOUT_TURNS = 20
MCTS_REPLAN_TURNS = 5
DLS_DEPTH = 5
AMBUSH_MAX_WAIT = 6  # Tom waits at most this many turns in ambush before sweeping instead
NORMAL_FLEE_RANGE = 2  # NORMAL EVADE: one-step flee only when Tom is this close, else A* to goal
CLOSE_RANGE = 4
# agent mode details (4.5)
SWEEP_STALE_TURNS = 20  # Tom SWEEP: a cell not seen for this many turns counts as unseen
JERRY_MEMORY_TURNS = 6  # Jerry uses Tom's last seen cell for at most this many turns
RISK_RADIUS = 6  # risk(cell) = max(0, RISK_RADIUS - d_tom(cell)) / RISK_RADIUS
RISK_WEIGHT = 4  # Jerry A* entry cost = 1 + RISK_WEIGHT * risk (+ dead-end cost)
DEAD_END_COST = 3
DEAD_END_ALERT_DIST = 8  # dead-end cost applies while Tom is within this distance
EVADE_FLOOD_WEIGHT = 0.5
EVADE_DEAD_END_PENALTY = 5
BRUNO_FEAR_RANGE = 8  # Tom fuzzy input bruno = max(0, 1 - d(Bruno, Tom) / 8)
# minimax evaluation weights (4.6), Tom perspective
W_DIST = -10
W_GOAL = 2
W_ESCAPE = -3
W_BRUNO_NEAR = -15
W_STUN = -8
W_DEAD_END = 5

# ---------------------------------------------------------------- window / UI (5)
WINDOW_W = 1100
WINDOW_H = 720
FPS = 60
TITLE = "Cheese Heist"
TOP_BAR_H = 48
BOARD_X = 0
BOARD_Y = TOP_BAR_H
BOARD_PX = 672  # square board area; tile = BOARD_PX // size
PANEL_X = 672
PANEL_W = WINDOW_W - PANEL_X  # 428
EVENT_LOG_LINES = 6
FOG_ALPHA = 165  # 65% black

# palette
COLOR_BG = (18, 22, 32)
COLOR_PANEL = (24, 29, 41)
COLOR_PANEL_LINE = (52, 60, 80)
COLOR_TEXT = (226, 230, 240)
COLOR_TEXT_DIM = (140, 150, 170)
COLOR_FLOOR = (0x2B, 0x3A, 0x55)
COLOR_WALL = (0x10, 0x15, 0x1F)
COLOR_WALL_EDGE = (0x3A, 0x45, 0x5C)
COLOR_CHEESE = (0xFF, 0xD2, 0x3F)
COLOR_EXIT_LOCKED = (0xC0, 0x39, 0x2B)
COLOR_EXIT_OPEN = (0x2E, 0xCC, 0x71)
COLOR_KENNEL = (0x8D, 0x6E, 0x63)
COLOR_TOM = (0xF3, 0x8B, 0x2A)
COLOR_JERRY = (0xA8, 0xA8, 0xB0)
COLOR_JERRY_EAR = (0xE8, 0xA0, 0xA8)
COLOR_BRUNO = (0x6D, 0x4C, 0x41)
COLOR_SPIKE = (0xE0, 0xE0, 0xE0)
COLOR_STAR = (0xFF, 0xF0, 0x80)
COLOR_ACCENT = (0x4F, 0xA3, 0xF7)
COLOR_PATH = (0x2E, 0xCC, 0x71)
COLOR_EXPLORED = (0x4F, 0xA3, 0xF7)

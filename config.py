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
MAX_MAZE_ATTEMPTS = 1000  # derived seeds tried before giving up
PLACEMENT_TRIES = 20  # feature placements tried on one carved maze

# ---------------------------------------------------------------- rules (3.2-3.7)
TURN_LIMIT = 120
VISION_RADIUS = 5  # BFS path distance (the fog; AIs ignore it while AI_FULL_INFO)
AI_FULL_INFO = True  # AI observations show both characters and Bruno everywhere (user decision)
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

# ---------------------------------------------------------------- pressure (3.9, 3.10)
SCENT_START_TURN = 50  # from this turn Tom gets a scent of Jerry (see game.end_of_round)
SCENT_PERIOD = 8  # every this many turns after SCENT_START_TURN
TRAP_LIMIT = 2  # mouse traps Jerry can set per game (human Jerry only)
TRAP_STUN = 2  # Tom's stun when he springs a trap
WHISTLE_COOLDOWN = 8  # turns between two whistles

# ---------------------------------------------------------------- AI (4.x, used from phase 2)
MINIMAX_MS_BUDGET = 100  # time safety net per move; node/iteration caps decide normally
MCTS_MS_BUDGET = 300
BRUNO_FEAR_RANGE = 8  # Tom fuzzy input bruno = max(0, 1 - d(Bruno, Tom) / 8)
# fuzzy mode -> factors on the minimax evaluation terms (dist, goal, escape, bruno)
MODE_SCALE = {
    "HUNT": (1.5, 1.0, 1.0, 1.0), "AMBUSH": (0.5, 3.0, 1.0, 1.0),
    "RETREAT": (0.5, 1.0, 1.0, 3.0), "SWEEP": (1.0, 1.0, 1.0, 1.0),
    "SNEAK": (0.5, 3.0, 1.0, 1.0), "EVADE": (2.0, 1.0, 2.0, 1.0),
    "RUN_FOR_BRUNO": (1.0, 3.0, 1.0, 1.0), "DASH": (0.5, 4.0, 1.0, 1.0),
}
CORNER_CHECK_DIST = 10  # Jerry checks she is not cornered while Tom is this close
MIN_ROOM = 10  # cells she must still reach before Tom after a move, else it is a trap
INTERCEPT_MIN_DIST = 4  # closer than this Tom chases directly instead of intercepting
W_AIM = -10  # Tom: per step from the interception cell (see agents.AIAgent.intercept)
LOOP_WINDOW = 16  # turns of (own cell, opponent cell) history kept for loop detection
STILL_TURNS = 5  # Jerry standing still this many turns in a row = hiding: commit to a route
LOOP_COMMIT_TURNS = 8  # turns a loop breaker commits once a loop is seen
MINIMAX_DEPTH = 4
MINIMAX_NODE_CAP = 20000
MCTS_ITERATIONS = 300
MCTS_UCB_C = 1.4
MCTS_PLAYOUT_TURNS = 20
MCTS_REPLAN_TURNS = 5
# minimax evaluation weights (4.6), Tom perspective
W_DIST = -10  # per step of d(Tom, Jerry) up to NEAR_DIST
W_DIST_FAR = -1  # per step beyond NEAR_DIST
NEAR_DIST = 8
W_KEYS = -100  # per key Jerry holds
W_GOAL = 2
W_ESCAPE = -3
W_BRUNO_NEAR = -15
W_STUN = -8
W_DEAD_END = 5

# ---------------------------------------------------------------- window / UI (5)
WINDOW_W = 1280  # logical canvas; SDL scales it to the window or the full screen (F11)
WINDOW_H = 800
FPS = 60
TITLE = "Cheese Heist"
TOP_BAR_H = 48
BOARD_X = 0
BOARD_Y = TOP_BAR_H
BOARD_PX = 736  # square board area; tile = BOARD_PX // size (35 px at 21x21)
PANEL_X = BOARD_PX
PANEL_W = WINDOW_W - PANEL_X  # 544
FONT_NAMES = ("bahnschrift", "segoeui", "arial")  # first installed family wins; else pygame default
EVENT_LOG_LINES = 6

# palette
COLOR_BG = (238, 242, 247)
COLOR_PANEL = (250, 251, 253)
COLOR_PANEL_LINE = (208, 215, 226)
COLOR_TEXT = (28, 34, 48)
COLOR_TEXT_DIM = (100, 110, 130)
COLOR_FLOOR = (0xDD, 0xD2, 0xB8)
COLOR_WALL = (0x6B, 0x7A, 0x9A)
COLOR_WALL_EDGE = (0x9F, 0xAE, 0xCB)
COLOR_CHEESE = (0xF2, 0xB1, 0x00)
COLOR_EXIT_LOCKED = (0xC0, 0x39, 0x2B)
COLOR_EXIT_OPEN = (0x2E, 0xCC, 0x71)
COLOR_KENNEL = (0x8D, 0x6E, 0x63)
COLOR_TOM = (0xF3, 0x8B, 0x2A)
COLOR_JERRY = (0xA8, 0xA8, 0xB0)
COLOR_JERRY_EAR = (0xE8, 0xA0, 0xA8)
COLOR_BRUNO = (0x6D, 0x4C, 0x41)
COLOR_TRAP = (0xE5, 0x39, 0x35)
COLOR_SPIKE = (0xB0, 0xB0, 0xB0)
COLOR_STAR = (0xF0, 0xC0, 0x20)
COLOR_ACCENT = (0x25, 0x7B, 0xD9)
COLOR_BUTTON = (0x1D, 0x5F, 0xB0)  # filled buttons: 6.3:1 with COLOR_ON_BUTTON
COLOR_ON_BUTTON = (0xFF, 0xFF, 0xFF)
COLOR_PATH = (0x2E, 0xCC, 0x71)
COLOR_EXPLORED = (0x4F, 0xA3, 0xF7)

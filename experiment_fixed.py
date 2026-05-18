import pygame
import csv
import time
import random
import os
import json
import math

# --- CONFIGURATION ---
SCREEN_WIDTH  = 1400          
SCREEN_HEIGHT = 800            
CURSOR_RADIUS = 28            
TARGET_RADIUS = 40            
HOMING_RADIUS = 70            
CENTER_TOLERANCE = 5          
DWELL_SECONDS = 1.0           
TARGET_APPEAR_DELAY = 1.0     
FPS = 60
FILE_NAME = "experiment_data.csv"
SUMMARY_FILE = "experiment_summary.csv"
RECORDING_DIR = "recordings"
NUM_ITERATIONS = 20
NUM_PRACTICE_ITERATIONS = 5

# Colors
WHITE      = (255, 255, 255)
BLACK      = (0, 0, 0)
RED        = (255, 0, 0)
BLUE       = (0, 0, 255)
GREEN      = (0, 200, 0)
GRAY       = (128, 128, 128)
LIGHT_GRAY = (220, 220, 220)

# Game Modes
PRACTICE    = "practice"
INDIVIDUAL  = "individual"
COOPERATIVE = "cooperative"
PLAYBACK    = "playback"
AI          = "ai"

# AI Control modes
AI_CONTROLS_VERTICAL   = 1
AI_CONTROLS_HORIZONTAL = 0

# Target locations for 20 iterations
TARGET_DISTANCE_CM = 12.8
PX_PER_CM = 28
TARGET_DISTANCE_PX = int(TARGET_DISTANCE_CM * PX_PER_CM)
TARGET_ANGLES = [0, 22.5, 45, 67.5, 90]

def generate_target_positions():
    targets = []
    center_x = SCREEN_WIDTH // 2
    center_y = SCREEN_HEIGHT // 2
    for angle in TARGET_ANGLES:
        for _ in range(4):
            radians = math.radians(angle)
            x = center_x + TARGET_DISTANCE_PX * math.cos(radians)
            y = center_y - TARGET_DISTANCE_PX * math.sin(radians)
            targets.append([int(x), int(y), angle])
    random.shuffle(targets)
    return targets

def get_ai_axis_for_iteration(iteration):
    """Split AI condition into 4 blocks of 5 trials."""
    block = (iteration - 1) // 5
    if block in [0, 2]:
        return AI_CONTROLS_VERTICAL
    else:
        return AI_CONTROLS_HORIZONTAL


class ExperimentGame:
    def __init__(self, screen, clock, mode=INDIVIDUAL, recording_file=None, iteration=1,
                 ai_axis=None, target_pos=None, target_angle=None, playback_axis=None,
                 num_iterations=NUM_ITERATIONS, participant_ids=None):
        self.screen = screen
        self.clock  = clock
        self.running = True
        self.mode = mode
        self.iteration = iteration
        self.num_iterations = num_iterations
        self.target_hit = False
        self.participant_ids = participant_ids or []

        self.target_angle = target_angle

        self.cursor_pos = [SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2]
        self.target_pos = target_pos if target_pos is not None else [SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2]

        self.human_v   = [0, 0]
        self.partner_v = [0, 0]

        self.data_log   = []
        self.start_time = time.time()
        self.dwell_frames = 0

        self.target_appear_time = None
        self.periphery_time     = None
        self.success_time       = None

        self.playback_frames = {'horizontal': [], 'vertical': []}
        self.playback_index  = 0
        self.playback_axis   = playback_axis
        if mode == PLAYBACK and recording_file:
            self.load_recording(recording_file)

        self.ai_control_axis = ai_axis if mode == AI else None

    # ------------------------------------------------------------------
    # Recording / Playback
    # ------------------------------------------------------------------

    def load_recording(self, filename):
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Recording file {filename} not found.")
            return

        iterations = data.get('iterations', [])
        if not iterations:
            print("Recording has no iterations.")
            return

        idx = self.iteration - 1
        if idx >= len(iterations):
            print(f"Recording has no data for iteration {self.iteration}.")
            return

        iter_data = iterations[idx]
        self.playback_frames['horizontal'] = iter_data.get('horizontal', [])
        self.playback_frames['vertical']   = iter_data.get('vertical', [])
        self.target_pos = iter_data.get('target_pos', self.target_pos)
        print(f"Loaded iteration {self.iteration}: "
              f"{len(self.playback_frames['horizontal'])} horizontal frames, "
              f"{len(self.playback_frames['vertical'])} vertical frames, "
              f"target={self.target_pos}")

    def get_playback_input(self):
        frames = self.playback_frames.get(self.playback_axis, [])
        if self.playback_index < len(frames):
            v = frames[self.playback_index]
            self.playback_index += 1
            return [v, 0] if self.playback_axis == 'horizontal' else [0, v]
        return [0, 0]

    # ------------------------------------------------------------------
    # AI
    # ------------------------------------------------------------------

    def get_ai_input(self):
        dx = self.target_pos[0] - self.cursor_pos[0]
        dy = self.target_pos[1] - self.cursor_pos[1]
        k  = 0.12
        if self.ai_control_axis == AI_CONTROLS_VERTICAL:
            return [0, dy * k]
        else:
            return [dx * k, 0]

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    # FIX 1: elapsed is now passed in as a parameter instead of being
    # referenced as an undefined local variable.
    def log_frame(self, phase, elapsed):
        pid = self.participant_ids[0] if self.participant_ids else ""

        self.data_log.append([
            pid,                    # 0  participant_id
            self.mode,              # 1  mode
            self.iteration,         # 2  iteration
            self.target_angle,      # 3  target_angle
            phase,                  # 4  phase
            elapsed,                # 5  timestamp
            self.cursor_pos[0],     # 6  cursor_x
            self.cursor_pos[1],     # 7  cursor_y
            self.human_v[0],        # 8  h_vx
            self.human_v[1],        # 9  h_vy
            self.partner_v[0],      # 10 p_vx
            self.partner_v[1],      # 11 p_vy
            self.target_pos[0],     # 12 target_x
            self.target_pos[1],     # 13 target_y
            self.ai_control_axis,   # 14 ai_axis
            self.playback_axis      # 15 playback_axis
        ])

    @staticmethod
    def _path_distance(frames):
        total = 0.0
        for i in range(1, len(frames)):
            dx = frames[i][0] - frames[i - 1][0]
            dy = frames[i][1] - frames[i - 1][1]
            total += (dx * dx + dy * dy) ** 0.5
        return round(total, 2)

    def save_data(self):
        frame_keys = ["participant_id", "mode", "iteration", "target_angle", "phase", "timestamp",
                      "cursor_x", "cursor_y", "h_vx", "h_vy", "p_vx", "p_vy",
                      "target_x", "target_y", "ai_axis", "playback_axis"]
        write_header = not os.path.exists(FILE_NAME)
        with open(FILE_NAME, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(frame_keys)
            w.writerows(self.data_log)
        print(f"Frame data saved to {FILE_NAME}")

        # FIX 2: filter on index 4 (phase), not index 1 (mode).
        # FIX 3: extract cursor_x/cursor_y from indices 6 and 7, not 3 and 4.
        approach_xy = [(r[6], r[7]) for r in self.data_log if r[4] == "approach"]
        homing_xy   = [(r[6], r[7]) for r in self.data_log if r[4] == "homing_in"]

        approach_rt = (round(self.periphery_time - self.target_appear_time, 4)
                       if self.periphery_time is not None and self.target_appear_time is not None
                       else "")
        homing_rt   = (round(self.success_time - self.periphery_time, 4)
                       if self.success_time is not None and self.periphery_time is not None
                       else "")

        pid = self.participant_ids[0] if self.participant_ids else ""
        summary_keys = ["participant_id", "consent", "mode", "iteration", "target_angle",
                        "phase", "reaction_time_s", "distance_px"]
        write_header = not os.path.exists(SUMMARY_FILE)
        with open(SUMMARY_FILE, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(summary_keys)
            w.writerow([pid, "yes", self.mode, self.iteration,
                        self.target_angle, "approach", approach_rt, self._path_distance(approach_xy)])
            w.writerow([pid, "yes", self.mode, self.iteration,
                        self.target_angle, "homing_in", homing_rt, self._path_distance(homing_xy)])
        print(f"Phase summary saved to {SUMMARY_FILE}")

    # ------------------------------------------------------------------
    # Drawing helper
    # ------------------------------------------------------------------

    def draw_text(self, text, font, color, surface, x, y):
        surface.blit(font.render(text, True, color), (x, y))

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        font           = pygame.font.Font(None, 24)
        countdown_font = pygame.font.Font(None, 72)
        speed          = 5
        dwell_needed        = int(DWELL_SECONDS * FPS)
        appear_delay_frames = int(TARGET_APPEAR_DELAY * FPS)
        frame_count = 0

        phase             = "pre_target"
        periphery_reached = False

        while self.running and not self.target_hit:
            self.screen.fill(WHITE)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False

            target_visible = frame_count >= appear_delay_frames

            keys = pygame.key.get_pressed()
            self.human_v   = [0, 0]
            self.partner_v = [0, 0]

            if self.mode in (PRACTICE, INDIVIDUAL):
                if keys[pygame.K_LEFT]:  self.human_v[0] = -speed
                if keys[pygame.K_RIGHT]: self.human_v[0] =  speed
                if keys[pygame.K_UP]:    self.human_v[1] = -speed
                if keys[pygame.K_DOWN]:  self.human_v[1] =  speed

            elif self.mode == COOPERATIVE:
                if keys[pygame.K_LEFT]:  self.human_v[0] = -speed
                if keys[pygame.K_RIGHT]: self.human_v[0] =  speed
                if keys[pygame.K_w]: self.partner_v[1] = -speed
                if keys[pygame.K_s]: self.partner_v[1] =  speed

            elif self.mode == PLAYBACK:
                if self.playback_axis == 'horizontal':
                    if keys[pygame.K_UP]:   self.human_v[1] = -speed
                    if keys[pygame.K_DOWN]: self.human_v[1] =  speed
                else:
                    if keys[pygame.K_LEFT]:  self.human_v[0] = -speed
                    if keys[pygame.K_RIGHT]: self.human_v[0] =  speed
                if target_visible:
                    self.partner_v = self.get_playback_input()

            elif self.mode == AI:
                if self.ai_control_axis == AI_CONTROLS_VERTICAL:
                    if keys[pygame.K_LEFT]:  self.human_v[0] = -speed
                    if keys[pygame.K_RIGHT]: self.human_v[0] =  speed
                else:
                    if keys[pygame.K_UP]:   self.human_v[1] = -speed
                    if keys[pygame.K_DOWN]: self.human_v[1] =  speed
                self.partner_v = self.get_ai_input() if target_visible and self.human_v != [0, 0] else [0, 0]

            self.cursor_pos[0] += self.human_v[0] + self.partner_v[0]
            self.cursor_pos[1] += self.human_v[1] + self.partner_v[1]
            self.cursor_pos[0] = max(CURSOR_RADIUS, min(SCREEN_WIDTH  - CURSOR_RADIUS, self.cursor_pos[0]))
            self.cursor_pos[1] = max(CURSOR_RADIUS, min(SCREEN_HEIGHT - CURSOR_RADIUS, self.cursor_pos[1]))

            # FIX 1: elapsed computed before log_frame and passed in explicitly.
            elapsed = time.time() - self.start_time

            if target_visible:
                if self.target_appear_time is None:
                    self.target_appear_time = elapsed
                    phase = "approach"

                dist = ((self.cursor_pos[0] - self.target_pos[0]) ** 2 +
                        (self.cursor_pos[1] - self.target_pos[1]) ** 2) ** 0.5

                if not periphery_reached and dist <= HOMING_RADIUS:
                    periphery_reached = True
                    self.periphery_time = elapsed
                    phase = "homing_in"

                if dist <= CENTER_TOLERANCE:
                    self.dwell_frames += 1
                    if self.dwell_frames >= dwell_needed:
                        self.success_time = elapsed
                        self.target_hit   = True
                        print(f"Target Hit! Iteration {self.iteration} complete.")
                else:
                    self.dwell_frames = 0

                target_color = GREEN if self.dwell_frames > 0 else RED
                pygame.draw.circle(self.screen, target_color, self.target_pos, TARGET_RADIUS)

                if self.dwell_frames > 0:
                    progress = self.dwell_frames / dwell_needed
                    arc_rect = pygame.Rect(
                        self.target_pos[0] - TARGET_RADIUS,
                        self.target_pos[1] - TARGET_RADIUS,
                        TARGET_RADIUS * 2, TARGET_RADIUS * 2
                    )
                    end_angle = -math.pi / 2 + progress * 2 * math.pi
                    pygame.draw.arc(self.screen, WHITE, arc_rect, -math.pi / 2, end_angle, 4)

            else:
                remaining = (appear_delay_frames - frame_count) / FPS
                surf = countdown_font.render(f"{remaining:.1f}", True, GRAY)
                self.screen.blit(surf, (
                    SCREEN_WIDTH  // 2 - surf.get_width()  // 2,
                    SCREEN_HEIGHT // 2 - surf.get_height() // 2 - 60
                ))

            pygame.draw.circle(self.screen, BLUE,
                               (int(self.cursor_pos[0]), int(self.cursor_pos[1])), CURSOR_RADIUS)

            self.draw_text(
                f"Mode: {self.mode.upper()} | Iteration: {self.iteration}/{self.num_iterations}",
                font, BLACK, self.screen, 10, 10)

            if self.mode in (PRACTICE, INDIVIDUAL):
                self.draw_text("Controls: Arrow Keys (all directions)", font, BLACK, self.screen, 10, 35)
            elif self.mode == COOPERATIVE:
                self.draw_text("P1: LEFT/RIGHT arrows  |  P2: W/S keys", font, BLACK, self.screen, 10, 35)
            elif self.mode == PLAYBACK:
                if self.playback_axis == 'horizontal':
                    self.draw_text("Playback: LEFT/RIGHT  |  You: UP/DOWN", font, BLACK, self.screen, 10, 35)
                else:
                    self.draw_text("Playback: UP/DOWN  |  You: LEFT/RIGHT", font, BLACK, self.screen, 10, 35)
            elif self.mode == AI:
                ai_txt  = "UP/DOWN"    if self.ai_control_axis == AI_CONTROLS_VERTICAL else "LEFT/RIGHT"
                you_txt = "LEFT/RIGHT" if self.ai_control_axis == AI_CONTROLS_VERTICAL else "UP/DOWN"
                self.draw_text(f"AI controls: {ai_txt}  |  You control: {you_txt}",
                               font, BLACK, self.screen, 10, 35)

            self.draw_text("ESC to quit", font, GRAY, self.screen, 10, 60)

            # FIX 1: pass elapsed into log_frame
            self.log_frame(phase, elapsed)
            frame_count += 1
            pygame.display.flip()
            self.clock.tick(FPS)

        if self.target_hit:
            self.save_data()


# ----------------------------------------------------------------------
# Session recording
# ----------------------------------------------------------------------

def save_session_recording(mode, session_records, filename=None):
    if not os.path.exists(RECORDING_DIR):
        os.makedirs(RECORDING_DIR)
    if filename is None:
        filename = os.path.join(RECORDING_DIR, f"session_{mode}_{int(time.time())}.json")
    data = {
        'mode': mode,
        'num_iterations': len(session_records),
        'timestamp': int(time.time()),
        'iterations': session_records
    }
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Session recording saved: {filename} ({len(session_records)} iterations)")
    return filename


# ----------------------------------------------------------------------
# Participant ID input screen
# ----------------------------------------------------------------------

def show_id_input_screen(screen, clock, mode):
    """Returns list of IDs, or None if cancelled."""
    font       = pygame.font.Font(None, 48)
    small_font = pygame.font.Font(None, 30)

    labels       = ["Player 1 ID:", "Player 2 ID:"] if mode == COOPERATIVE else ["Participant ID:"]
    values       = [""] * len(labels)
    active_field = 0

    while True:
        screen.fill(WHITE)

        title = font.render("Enter Participant ID", True, BLACK)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 120))

        sub = small_font.render(
            "TAB or ENTER to move between fields. ENTER on last field to continue.", True, GRAY)
        screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 185))

        for i, (label, value) in enumerate(zip(labels, values)):
            y = 280 + i * 130
            screen.blit(font.render(label, True, BLACK), (250, y))

            box_rect  = pygame.Rect(250, y + 52, 600, 56)
            box_color = BLUE if i == active_field else GRAY
            pygame.draw.rect(screen, LIGHT_GRAY, box_rect)
            pygame.draw.rect(screen, box_color, box_rect, 3)

            display_text = value + ("|" if i == active_field else "")
            screen.blit(font.render(display_text, True, BLACK), (box_rect.x + 12, box_rect.y + 10))

        screen.blit(small_font.render("ESC to cancel", True, GRAY),
                    (SCREEN_WIDTH // 2 - 60, 680))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                elif event.key == pygame.K_TAB:
                    active_field = (active_field + 1) % len(labels)
                elif event.key == pygame.K_RETURN:
                    if active_field < len(labels) - 1:
                        active_field += 1
                    else:
                        return values
                elif event.key == pygame.K_BACKSPACE:
                    values[active_field] = values[active_field][:-1]
                elif event.unicode.isprintable():
                    values[active_field] += event.unicode

        clock.tick(FPS)


# ----------------------------------------------------------------------
# Ethics / Consent Screen
# ----------------------------------------------------------------------

def show_consent_screen(screen, clock):
    title_font = pygame.font.Font(None, 48)
    text_font  = pygame.font.Font(None, 24)
    small_font = pygame.font.Font(None, 22)

    consent_lines = [
        "INFORMED CONSENT",
        "",
        "You are invited to participate in a study about joint action and movement coordination.",
        "",
        "During this experiment, your keyboard movements and task performance",
        "will be recorded anonymously for research purposes.",
        "",
        "Participation is voluntary.",
        "You may stop the experiment at any time without penalty.",
        "",
        "No personally identifying information will be stored with the data.",
        "",
        "By continuing, you confirm that:",
        "• you are at least 18 years old",
        "• you voluntarily agree to participate",
        "• you understand that you can withdraw at any time",
        "",
        "Press Y to consent and continue.",
        "Press N or ESC to decline."
    ]

    while True:
        screen.fill(WHITE)

        title = title_font.render("Participant Consent", True, BLACK)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 60))

        y = 130
        for line in consent_lines:
            color = RED if "Press Y" in line or "Press N" in line else BLACK
            surf = text_font.render(line, True, color)
            screen.blit(surf, (80, y))
            y += 30

        footer = small_font.render("ESC = decline participation", True, GRAY)
        screen.blit(footer, (SCREEN_WIDTH // 2 - 120, SCREEN_HEIGHT - 45))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_y:
                    return True
                if event.key == pygame.K_n:
                    return False
                if event.key == pygame.K_ESCAPE:
                    return False

        clock.tick(FPS)


# ----------------------------------------------------------------------
# Mode selection menu
# ----------------------------------------------------------------------

def show_menu(screen, clock):
    font       = pygame.font.Font(None, 72)
    small_font = pygame.font.Font(None, 42)

    selected = 0
    modes = [
        (PRACTICE,    "0. Practice Mode  (5 trials, warm-up)"),
        (INDIVIDUAL,  "1. Individual Mode  (you control alone)"),
        (COOPERATIVE, "2. Cooperative Mode  (2 players)"),
        (PLAYBACK,    "3. Playback Mode  (play with your own recording)"),
        (AI,          "4. AI Mode  (play with AI agent)")
    ]

    while True:
        screen.fill(WHITE)
        title = font.render("Select Game Mode", True, BLACK)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 80))

        for i, (_, label) in enumerate(modes):
            color  = BLUE if i == selected else BLACK
            prefix = ">>> " if i == selected else "    "
            screen.blit(small_font.render(prefix + label, True, color),
                        (SCREEN_WIDTH // 2 - 380, 230 + i * 90))

        info = small_font.render(
            f"Each mode runs {NUM_ITERATIONS} iterations  (Practice: {NUM_PRACTICE_ITERATIONS})", True, GRAY)
        screen.blit(info, (SCREEN_WIDTH // 2 - info.get_width() // 2, 700))
        instr = small_font.render("UP/DOWN = select   ENTER = confirm   ESC = exit", True, GRAY)
        screen.blit(instr, (SCREEN_WIDTH // 2 - instr.get_width() // 2, 750))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:     selected = (selected - 1) % len(modes)
                if event.key == pygame.K_DOWN:   selected = (selected + 1) % len(modes)
                if event.key == pygame.K_RETURN:
                    return modes[selected][0]
                if event.key == pygame.K_ESCAPE:
                    return None
        clock.tick(FPS)


# ----------------------------------------------------------------------
# Recording selection menu
# ----------------------------------------------------------------------

def show_recording_menu(screen, clock):
    font       = pygame.font.Font(None, 60)
    small_font = pygame.font.Font(None, 32)

    recordings = []
    if os.path.exists(RECORDING_DIR):
        recordings = sorted([f for f in os.listdir(RECORDING_DIR) if f.endswith('.json')],
                            reverse=True)

    if not recordings:
        screen.fill(WHITE)
        screen.blit(small_font.render(
            "No recordings found. Run INDIVIDUAL or COOPERATIVE mode first.", True, BLACK),
            (SCREEN_WIDTH // 2 - 350, SCREEN_HEIGHT // 2))
        pygame.display.flip()
        pygame.time.wait(2000)
        return None

    selected = 0
    while True:
        screen.fill(WHITE)
        title = font.render("Select Recording to Play", True, BLACK)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 60))

        for i, rec in enumerate(recordings[:12]):
            color  = BLUE if i == selected else BLACK
            prefix = ">>> " if i == selected else "    "
            screen.blit(small_font.render(prefix + rec, True, color), (160, 160 + i * 45))

        screen.blit(small_font.render("UP/DOWN = select   ENTER = confirm   ESC = cancel", True, GRAY),
                    (SCREEN_WIDTH // 2 - 240, 730))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:    selected = (selected - 1) % min(len(recordings), 12)
                if event.key == pygame.K_DOWN:  selected = (selected + 1) % min(len(recordings), 12)
                if event.key == pygame.K_RETURN:
                    return os.path.join(RECORDING_DIR, recordings[selected])
                if event.key == pygame.K_ESCAPE:
                    return None
        clock.tick(FPS)


# ----------------------------------------------------------------------
# Per-iteration ready screen
# ----------------------------------------------------------------------

def show_iteration_ready_screen(screen, clock, mode, iteration, total,
                                ai_axis=None, playback_axis=None):
    font       = pygame.font.Font(None, 64)
    small_font = pygame.font.Font(None, 36)

    while True:
        screen.fill(WHITE)
        screen.blit(font.render(f"Iteration {iteration} of {total}", True, BLACK),
                    (SCREEN_WIDTH // 2 - 160, 70))
        screen.blit(small_font.render("Controls:", True, BLACK), (200, 185))

        y = 230
        if mode in (PRACTICE, INDIVIDUAL):
            screen.blit(small_font.render("Arrow Keys — control the ball in all directions",
                                          True, BLACK), (220, y))
        elif mode == COOPERATIVE:
            screen.blit(small_font.render("Player 1: LEFT/RIGHT arrows (horizontal)", True, BLACK), (220, y))
            screen.blit(small_font.render("Player 2: W/S keys (vertical)",            True, BLACK), (220, y + 38))
        elif mode == PLAYBACK:
            if playback_axis == 'horizontal':
                screen.blit(small_font.render("Playback controls: LEFT/RIGHT (horizontal)", True, BLUE),  (220, y))
                screen.blit(small_font.render("You control: UP/DOWN (vertical) with Arrow Keys", True, BLACK), (220, y + 38))
            else:
                screen.blit(small_font.render("Playback controls: UP/DOWN (vertical)",   True, BLUE),  (220, y))
                screen.blit(small_font.render("You control: LEFT/RIGHT (horizontal) with Arrow Keys", True, BLACK), (220, y + 38))
        elif mode == AI:
            block_number = ((iteration - 1) // 5) + 1
            ai_ctrl  = "UP/DOWN"           if ai_axis == AI_CONTROLS_VERTICAL else "LEFT/RIGHT"
            you_ctrl = "LEFT/RIGHT arrows" if ai_axis == AI_CONTROLS_VERTICAL else "UP/DOWN arrows"
            screen.blit(small_font.render(f"AI Block {block_number} of 4", True, BLUE),  (220, y))
            screen.blit(small_font.render(f"AI controls: {ai_ctrl}",        True, BLACK), (220, y + 45))
            screen.blit(small_font.render(f"You control: {you_ctrl}",       True, BLACK), (220, y + 90))

        screen.blit(small_font.render("Goal: move the BLUE ball into the RED target", True, BLACK), (200, 390))
        screen.blit(small_font.render("Move the cursor exactly on the target as fast as possible,", True, RED), (200, 430))
        screen.blit(small_font.render("using the most direct path possible!", True, RED), (200, 465))

        screen.blit(font.render("Press SPACE to start", True, BLUE),
                    (SCREEN_WIDTH // 2 - 220, 560))
        screen.blit(small_font.render("ESC to return to menu", True, GRAY),
                    (SCREEN_WIDTH // 2 - 130, 650))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    return True
                if event.key == pygame.K_ESCAPE:
                    return False
        clock.tick(FPS)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("CogSci Joint Action Task")
    clock = pygame.time.Clock()

    consent_given = show_consent_screen(screen, clock)
    if not consent_given:
        print("Participant declined consent. Exiting.")
        pygame.quit()
        raise SystemExit

    while True:
        mode = show_menu(screen, clock)
        if mode is None:
            print("Exiting game.")
            break

        num_iterations = NUM_PRACTICE_ITERATIONS if mode == PRACTICE else NUM_ITERATIONS

        participant_ids = []
        if mode != PRACTICE:
            participant_ids = show_id_input_screen(screen, clock, mode)
            if participant_ids is None:
                print("ID entry cancelled. Returning to menu.")
                continue
            id_str = " | ".join(f"P{i+1}: {pid}" for i, pid in enumerate(participant_ids))
            print(f"Session started — {id_str}")

        recording_file = None
        if mode == PLAYBACK:
            recording_file = show_recording_menu(screen, clock)
            if recording_file is None:
                print("No recording selected. Returning to menu.")
                continue

        individual_save_path = None
        if mode == INDIVIDUAL:
            if not os.path.exists(RECORDING_DIR):
                os.makedirs(RECORDING_DIR)
            pid = participant_ids[0] if participant_ids else "unknown"
            individual_save_path = os.path.join(
                RECORDING_DIR, f"session_{pid}_{int(time.time())}.json")
            print(f"Individual session will be saved to: {individual_save_path}")

        target_positions = generate_target_positions()
        session_records  = []
        user_cancelled   = False

        for iteration in range(1, num_iterations + 1):
            ai_axis = None
            if mode == AI:
                ai_axis = get_ai_axis_for_iteration(iteration)

            playback_axis = None
            if mode == PLAYBACK:
                playback_axis = random.choice(['horizontal', 'vertical'])
                print(f"Iteration {iteration}: playback axis = {playback_axis}")

            target_info  = target_positions[iteration - 1]
            target_pos   = [target_info[0], target_info[1]]
            target_angle = target_info[2]

            if not show_iteration_ready_screen(screen, clock, mode, iteration, num_iterations,
                                               ai_axis=ai_axis, playback_axis=playback_axis):
                print(f"User cancelled at iteration {iteration}. Returning to menu.")
                user_cancelled = True
                break

            game = ExperimentGame(
                screen=screen,
                clock=clock,
                mode=mode,
                recording_file=recording_file,
                iteration=iteration,
                ai_axis=ai_axis,
                target_pos=target_pos,
                target_angle=target_angle,
                playback_axis=playback_axis,
                num_iterations=num_iterations,
                participant_ids=participant_ids
            )
            game.run()

            if not game.running and not game.target_hit:
                print(f"User cancelled during iteration {iteration}. Returning to menu.")
                user_cancelled = True
                break

            # FIX 4: record cursor_x/cursor_y from the correct indices (6 and 7),
            # and velocities from the correct indices (8-11).
            record = {
                'iteration':   iteration,
                'target_pos':  game.target_pos,
                'target_angle': game.target_angle,
                'horizontal':  [entry[8]  for entry in game.data_log],  # h_vx
                'vertical':    [entry[9]  for entry in game.data_log],  # h_vy
            }
            if mode == COOPERATIVE:
                record['human_horizontal']   = [entry[8]  for entry in game.data_log]  # h_vx
                record['human_vertical']     = [entry[9]  for entry in game.data_log]  # h_vy
                record['partner_horizontal'] = [entry[10] for entry in game.data_log]  # p_vx
                record['partner_vertical']   = [entry[11] for entry in game.data_log]  # p_vy

            session_records.append(record)

            if mode == INDIVIDUAL and individual_save_path:
                save_session_recording(mode, session_records, individual_save_path)

        if not user_cancelled:
            if mode == COOPERATIVE and session_records:
                path = save_session_recording(mode, session_records)
                print(f"Cooperative session saved: {path}")

            print(f"\nCompleted all {num_iterations} iterations of {mode.upper()} mode!")
            print("Returning to menu...")

    pygame.quit()

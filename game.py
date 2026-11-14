import asyncio
import math
import os
import random
from collections import deque

import pygame

import art
import audio
import data
import events
import fx
import levels
import scoring
import treasure
import ui
from sprites import (
    TILE_SIZE, Coin, Puddle, Player, Monster, MONSTER_COLORS,
    draw_sand_background, draw_heart, load_coin_frames,
    draw_pirate_avatar, vertical_gradient,
)

LOGICAL_W, LOGICAL_H = 900, 600
HUD_H = 60
FPS = 60
MAX_LIVES = 3
DIGS_PER_ISLAND = 3
ISLAND_PAD = 12

TITLE = "title"
PLAYING = "playing"
LEVEL_COMPLETE = "level_complete"
GAME_OVER = "game_over"
WIN = "win"
LEADERBOARD = "leaderboard"

PANEL = (255, 250, 235)
INK = (50, 40, 30)
INK_SOFT = (107, 90, 72)
INK_LABEL = (138, 106, 68)
GOLD = art.GOLD
GOLD_LIT = art.GOLD_LIT
GOLD_DEEP = art.GOLD_DEEP
HUD_TOP = (92, 62, 40)
HUD_BOTTOM = (58, 38, 26)
HUD_EDGE = (30, 20, 14)
HUD_TEXT = (250, 236, 204)
HUD_DIM = (190, 160, 118)
GOOD = (60, 130, 70)
BAD = (170, 60, 50)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")


def load_font(size, display=False):
    """pygame's bundled face, so the desktop and the browser lay text out
    identically (the old SysFont("arial") silently became this on the web).
    Drop a display.ttf / body.ttf into assets/fonts to restyle the game."""
    path = os.path.join(FONT_DIR, "display.ttf" if display else "body.ttf")
    if os.path.exists(path):
        try:
            return pygame.font.Font(path, size)
        except Exception:
            pass
    return pygame.font.Font(None, size)


class Button:
    def __init__(self, rect, text, color=(226, 176, 70)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.enabled = True

    def draw(self, surface, font, mouse=(-1, -1)):
        if not self.enabled:
            pygame.draw.rect(surface, (206, 196, 176), self.rect, border_radius=12)
            pygame.draw.rect(surface, (160, 148, 128), self.rect, 3, border_radius=12)
            label = font.render(self.text, True, (135, 124, 106))
            surface.blit(label, label.get_rect(center=self.rect.center))
            return
        hovered = self.rect.collidepoint(mouse)
        col = tuple(min(255, c + 22) for c in self.color) if hovered else self.color
        lift = 1 if hovered else 0
        rect = self.rect.move(0, -lift)
        pygame.draw.rect(surface, (58, 34, 16), self.rect.move(0, 4), border_radius=12)
        pygame.draw.rect(surface, col, rect, border_radius=12)
        pygame.draw.line(surface, tuple(min(255, c + 40) for c in col),
                         (rect.x + 12, rect.y + 5), (rect.right - 12, rect.y + 5), 2)
        pygame.draw.rect(surface, (58, 34, 16), rect, 3, border_radius=12)
        for x in (rect.x + 11, rect.right - 11):       # brass rivets
            pygame.draw.circle(surface, (58, 34, 16), (x, rect.centery), 3)
        label = font.render(self.text, True, INK)
        surface.blit(label, label.get_rect(center=rect.center))

    def clicked(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Pirate Island: Treasure Hunt")
        self.window = pygame.display.set_mode((LOGICAL_W, LOGICAL_H), pygame.RESIZABLE)
        self.surface = pygame.Surface((LOGICAL_W, LOGICAL_H))
        self.clock = pygame.time.Clock()

        self.font_tiny = load_font(18)
        self.font_small = load_font(23)
        self.font_med = load_font(30)
        self.font_big = load_font(54, display=True)
        self.font_title = load_font(74, display=True)
        self.font_hud = load_font(28)
        self.font_label = load_font(15)
        self.font_pop = load_font(25)

        self.audio = audio.Audio()
        self.particles = fx.Particles()
        self.shake = fx.Shake()
        self.sea_fx = fx.Sea(LOGICAL_W, LOGICAL_H)
        self.rain = fx.Rain(LOGICAL_W, LOGICAL_H)

        # Backdrops that never change: built once rather than per frame.
        self.seas = {}
        self.hud_band = vertical_gradient(LOGICAL_W, HUD_H,
                                          [(0.0, HUD_TOP), (1.0, HUD_BOTTOM)])
        rnd = random.Random(11)
        for _ in range(26):                       # plank grain
            y = rnd.randint(4, HUD_H - 8)
            x = rnd.randint(0, LOGICAL_W)
            pygame.draw.line(self.hud_band, (74, 49, 32), (x, y), (x + rnd.randint(40, 160), y), 1)
        self.title_art = art.gold_title(self.font_title, "Pirate Island")
        self.lights = {}

        self.coin_frames = load_coin_frames()
        self.coin_icon = pygame.transform.smoothscale(self.coin_frames[0], (24, 24))
        self.scores = data.load_scores()

        self.running = True
        self.last_resize = None
        self.state = TITLE
        self.state_t = 0.0
        self.time = 0.0
        self.mouse = (0, 0)
        self.player_name = None
        self.save_score = True
        self.previous_best = 0
        self.level_index = 0
        self.lives = MAX_LIVES
        self.score = scoring.ScoreKeeper()
        self.shown_score = 0.0
        self.final_lines = []
        self.mood = art.MOODS["title"]

        # Title screen: pick a registered pirate, or type a fresh name.
        self.combo = ui.ComboBox((125, 226, 300, 46))
        self.name_field = ui.TextField((475, 226, 300, 46), max_len=data.MAX_NAME_LEN)
        self.save_checkbox = ui.Checkbox((475, 292), "Save my name and score", checked=True)
        self.play_button = Button((240, 490, 200, 54), "Set Sail!")
        self.fame_button = Button((460, 490, 200, 54), "Hall of Fame", (196, 170, 126))
        self.refresh_roster()

        self.continue_button = Button((350, 500, 200, 50), "Continue")
        self.retry_button = Button((240, 536, 200, 48), "Sail Again")
        self.port_button = Button((460, 536, 200, 48), "Back to Port", (196, 170, 126))
        self.back_button = Button((350, 532, 200, 48), "Back to Port")
        self.resume_button = Button((350, 280, 200, 50), "Resume")
        self.quit_button = Button((350, 346, 200, 50), "Abandon Voyage", (196, 170, 126))

        # In-play overlays and feedback.
        self.scroll = None
        self.paused = False
        self.banner = None
        self.toasts = []
        self.flash = 0.0
        self.hurt_flash = 0.0
        self.director = None

        self.audio.loop(audio.MUSIC, "shanty")
        self.audio.loop(audio.SEA, "waves")

    def refresh_roster(self):
        self.combo.set_items(data.ranking(self.scores))

    def sea(self, mood_name):
        if mood_name not in self.seas:
            self.seas[mood_name] = vertical_gradient(LOGICAL_W, LOGICAL_H,
                                                     art.MOODS[mood_name]["sea"])
        return self.seas[mood_name]

    def set_state(self, state):
        self.state = state
        self.state_t = 0.0

    # -------------------------------------------------------- title screen
    def chosen_name(self):
        """The name the Set Sail button would use, or "" when nothing is picked."""
        typed = data.clean_name(self.name_field.text)
        if typed:
            return data.find_player(self.scores, typed) or typed
        return self.combo.selected or ""

    def typing_new_name(self):
        return bool(data.clean_name(self.name_field.text))

    def handle_title_click(self, pos):
        action = self.combo.click(pos)
        if action:
            self.audio.play("click")
            if action == "selected":
                # Picking from the list wins over a half-typed name.
                self.name_field.text = ""
                self.name_field.focused = False
            return
        if self.name_field.click(pos):
            self.combo.selected = None
            return
        if self.typing_new_name() and self.save_checkbox.click(pos):
            self.audio.play("click")
            return
        if self.play_button.clicked(pos):
            self.begin_from_title()
        elif self.fame_button.clicked(pos):
            self.audio.play("click")
            self.set_state(LEADERBOARD)

    def begin_from_title(self):
        name = self.chosen_name()
        if not name:
            return
        # An existing pirate is already on the roster; the checkbox only governs
        # whether a newly typed name gets registered.
        save = True if not self.typing_new_name() else self.save_checkbox.checked
        self.audio.play("bell")
        self.start_new_game(name, save)

    def handle_title_key(self, event):
        if self.name_field.key(event):
            if self.name_field.text:
                self.combo.selected = None
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.begin_from_title()
        elif event.key == pygame.K_ESCAPE:
            self.combo.open = False
            self.name_field.focused = False
        elif event.key == pygame.K_m:
            self.toggle_mute()

    def back_to_title(self):
        self.name_field.text = ""
        self.name_field.focused = False
        self.combo.open = False
        if self.player_name:
            self.combo.selected = self.player_name if self.save_score else None
        if self.director:
            self.director.stop()
            self.director = None
        self.scroll = None
        self.paused = False
        self.mood = art.MOODS["title"]
        self.audio.loop(audio.MUSIC, "shanty")
        self.audio.loop(audio.WEATHER, None)
        self.set_state(TITLE)

    # ---------------------------------------------------------- level setup
    def load_level(self, index):
        """index 0-4 are the charted islands; index 5 is the secret cove."""
        self.level_index = index
        self.is_secret = index >= len(levels.LEVELS)
        cfg = levels.SECRET if self.is_secret else levels.LEVELS[index]
        self.cfg = cfg
        self.level_number = index + 1
        grid = cfg["grid"]
        rows, cols = len(grid), len(grid[0])
        self.rows, self.cols = rows, cols

        self.grid_px_w = cols * TILE_SIZE
        self.grid_px_h = rows * TILE_SIZE
        self.ox = (LOGICAL_W - self.grid_px_w) // 2
        self.oy = HUD_H + (LOGICAL_H - HUD_H - self.grid_px_h) // 2
        self.bounds = pygame.Rect(0, 0, self.grid_px_w, self.grid_px_h)

        self.coins = []
        self.puddles = []
        self.monsters = []
        self.plates = {}
        self.vault_doors = []
        self.crown = None
        wall_tiles = []
        player_start = (1, 1)

        color = (196, 232, 220) if self.is_secret else MONSTER_COLORS[index % len(MONSTER_COLORS)]
        self.monster_color = color
        for r, row in enumerate(grid):
            for c, ch in enumerate(row):
                if ch == '#':
                    wall_tiles.append((c, r))
                elif ch == 'C':
                    coin = Coin(c, r, self.coin_frames)
                    coin.value = scoring.COIN_VALUE
                    self.coins.append(coin)
                elif ch == '~':
                    self.puddles.append(Puddle(c, r))
                elif ch == 'M':
                    self.monsters.append(Monster(c, r, color, cfg["monster_speed"],
                                                 cfg["monster_mode"]))
                elif ch == 'P':
                    player_start = (c, r)
                elif ch == 'V':
                    self.vault_doors.append((c, r))
                elif ch == 'K':
                    self.crown = (c, r)
                elif ch in '1234':
                    self.plates[(c, r)] = treasure.RUNES[int(ch) - 1]

        self.start_tile = player_start
        self.wall_tiles = wall_tiles
        self.wall_rects = [pygame.Rect(c * TILE_SIZE, r * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                           for c, r in wall_tiles + self.vault_doors]
        blocked = set(wall_tiles) | set(self.vault_doors)
        self.walk_tiles = {(c, r) for r in range(rows) for c in range(cols)
                           if (c, r) not in blocked}
        self.sand_tiles = treasure.open_tiles(grid)
        self.player = Player(*player_start)
        self.player.start_invincibility(1.2)      # a breath before the crabs count
        self.total_coins = len(self.coins)
        self.coins_collected_level = 0

        # The island's secret.
        self.holes = set()
        self.digs_left = DIGS_PER_ISLAND
        self.digs_used = 0
        self.dig_cool = 0.0
        self.chest_found = False
        self.chest_t = 0.0
        self.bottle_taken = False
        self.clue = None
        self.vault_open = False
        self.rune_progress = 0
        self.rune_mistakes = 0
        self.rune_bad_t = 0.0
        self.extra_crabs = 0
        if self.is_secret:
            self.plan = None
            self.runes = treasure.rune_plan()
            self.clue = self.runes
            self.reserved_tiles = set(self.plates) | {player_start}
            landmarks = []
            # The hoard behind the door is worth more than beach coins.
            for coin in self.coins:
                if 9 <= coin.col <= 11 and 5 <= coin.row <= 7:
                    coin.value = scoring.VAULT_COIN_VALUE
        else:
            self.plan = treasure.plan(grid, cfg["clue"], player_start)
            self.runes = None
            landmarks = self.plan["landmarks"]
            self.reserved_tiles = {self.plan["chest"], self.plan["bottle"], player_start} \
                | {tile for _, tile in landmarks}

        self.mood = art.MOODS[cfg["mood"]]
        self.bake_island(grid, landmarks, index)
        self.light = None
        if self.mood["dark"]:
            key = cfg["mood"]
            if key not in self.lights:
                self.lights[key] = art.lantern_light(
                    self.surface, self.mood["dark"], self.mood["glow"], 250 if self.is_secret else 220)
            self.light = self.lights[key]

        self.prev_tile = None
        self.dist = {}
        self.update_field(force=True)
        self.director = events.EventDirector(self, cfg["events"])
        self.particles.clear()
        self.toasts = []
        self.banner = None
        self.flash = self.hurt_flash = 0.0
        self.paused = False
        self.scroll = None
        self.score.start_level()

        self.audio.loop(audio.MUSIC, "drone" if self.is_secret else "shanty")
        self.audio.loop(audio.WEATHER, None)
        title = "THE HIDDEN COVE" if self.is_secret else f"ISLAND {self.level_number}"
        self.announce(f"{title}: {cfg['name'].upper()}",
                      "The vault wakes only to the right stones" if self.is_secret else
                      ("SPACE digs - find the bottle to learn where" if index == 0 else None),
                      (44, 92, 84) if self.is_secret else (150, 46, 40))
        if self.is_secret:
            self.open_scroll()
        self.set_state(PLAYING)

    def bake_island(self, grid, landmarks, seed):
        """Foam, sand, obstacles and landmarks flattened into one layer. None of
        it moves, so it is one blit a frame instead of a few hundred."""
        pad = ISLAND_PAD
        w, h = self.grid_px_w, self.grid_px_h
        layer = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        rect = pygame.Rect(pad, pad, w, h)
        pygame.draw.rect(layer, (255, 255, 255, 38), rect.inflate(22, 22), border_radius=31)
        pygame.draw.rect(layer, (255, 255, 255, 86), rect.inflate(10, 10), border_radius=25)
        layer.blit(draw_sand_background(w, h, self.cols, self.rows, 0, 0, seed=seed), (pad, pad))
        rnd = random.Random(seed * 131 + 7)
        for c, r in self.wall_tiles:
            kind = art.pick_obstacle(c, r, self.cols, self.rows, rnd)
            layer.blit(art.obstacle_tile(kind), (pad + c * TILE_SIZE, pad + r * TILE_SIZE))
        for kind, (c, r) in landmarks:
            art.draw_landmark(layer, kind, pad + c * TILE_SIZE + TILE_SIZE // 2,
                              pad + r * TILE_SIZE + TILE_SIZE // 2)
        layer.fill(self.mood["tint"], special_flags=pygame.BLEND_RGB_MULT)
        self.island = layer

    def start_new_game(self, player_name, save_score=True):
        self.player_name = player_name
        self.save_score = save_score
        if save_score:
            data.register_player(self.scores, player_name)
            self.refresh_roster()
        self.lives = MAX_LIVES
        self.score = scoring.ScoreKeeper()
        self.shown_score = 0.0
        self.load_level(0)

    # --------------------------------------------------------- game hooks
    def player_tile(self):
        return int(self.player.x // TILE_SIZE), int(self.player.y // TILE_SIZE)

    def update_field(self, force=False):
        """Steps-to-the-pirate for every walkable tile. Crabs walk down it,
        the golden crab walks up it. Rebuilt only when the pirate changes tile."""
        tile = self.player_tile()
        if tile == self.prev_tile and not force:
            return False
        changed = tile != self.prev_tile
        self.prev_tile = tile
        dist = {tile: 0}
        queue = deque([tile])
        walk = self.walk_tiles
        while queue:
            c, r = queue.popleft()
            d = dist[(c, r)] + 1
            for n in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                if n in walk and n not in dist:
                    dist[n] = d
                    queue.append(n)
        self.dist = dist
        return changed

    def announce(self, text, sub=None, color=(150, 46, 40)):
        self.banner = [text, sub, color, 0.0]

    def toast(self, text):
        self.toasts = [[text, 0.0]]

    def popup(self, text, x, y, color=GOLD_LIT, big=False):
        font = self.font_med if big else self.font_pop
        self.particles.text(art.outlined(font, text, color).copy(), x, y, 1.2 if big else 0.9)

    def award(self, category, points, label, sound=None, at=None):
        self.score.add(category, points)
        x, y = at or (self.player.x, self.player.y - 22)
        self.popup(f"+{points}  {label}", x, y - 8, GOLD_LIT, big=True)
        if sound:
            self.audio.play(sound)

    def toggle_mute(self):
        muted = self.audio.toggle_mute()
        if self.state == PLAYING:
            self.toast("Sound off" if muted else "Sound on")

    def open_scroll(self):
        if self.clue:
            self.scroll = self.clue
            self.scroll_t = 0.0

    # -------------------------------------------------------------- events
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            elif event.type == pygame.VIDEORESIZE:
                # Rebuild only on a genuinely new size. Calling set_mode for
                # every event makes the browser canvas oscillate: each call
                # resizes the canvas, which fires another resize, and the game
                # spends every frame re-creating the display instead of
                # reading input.
                size = (event.w, event.h)
                if size != self.window.get_size() and size != self.last_resize:
                    self.last_resize = size
                    self.window = pygame.display.set_mode(size, pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_click(self.to_logical_pos(event.pos))
            elif event.type == pygame.MOUSEWHEEL and self.state == TITLE:
                self.combo.wheel(self.to_logical_pos(pygame.mouse.get_pos()), event.y)
            elif event.type == pygame.KEYDOWN:
                if self.state == TITLE:
                    self.handle_title_key(event)
                else:
                    self.handle_key(event.key)

    def handle_key(self, key):
        confirm = key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
        if key == pygame.K_m:
            self.toggle_mute()
        elif self.state == PLAYING:
            if self.scroll:
                # A beat before it can be dismissed: SPACE is also the dig key,
                # and a pirate mid-mash should still get to read the message.
                if self.scroll_t > 0.4 and (confirm or key in (pygame.K_ESCAPE, pygame.K_c)):
                    self.scroll = None
            elif self.paused:
                if key in (pygame.K_p, pygame.K_ESCAPE) or confirm:
                    self.paused = False
                elif key == pygame.K_q:
                    self.back_to_title()
            elif key in (pygame.K_SPACE, pygame.K_e):
                self.try_dig()
            elif key == pygame.K_c:
                if self.clue:
                    self.open_scroll()
                else:
                    self.toast("No clue yet - look for a bottle washed up on the sand.")
            elif key in (pygame.K_p, pygame.K_ESCAPE):
                self.paused = True
        elif self.state == LEVEL_COMPLETE:
            if confirm and self.state_t > 0.4:
                self.advance()
        elif self.state in (GAME_OVER, WIN):
            if confirm:
                if self.state_t > 1.0:
                    self.sail_again()
            elif key == pygame.K_ESCAPE:
                self.back_to_title()
        elif self.state == LEADERBOARD:
            if confirm or key == pygame.K_ESCAPE:
                self.back_to_title()

    def viewport(self):
        """The largest 900x600-shaped rectangle that fits, centred.

        The browser hands us a canvas of whatever shape the page is, and a
        resized desktop window is no different: scaling to fill either one
        stretches the pirates. Letterbox instead.
        """
        ww, wh = self.window.get_size()
        scale = min(ww / LOGICAL_W, wh / LOGICAL_H)
        w = max(1, int(LOGICAL_W * scale))
        h = max(1, int(LOGICAL_H * scale))
        return (ww - w) // 2, (wh - h) // 2, w, h

    def to_logical_pos(self, pos):
        ox, oy, w, h = self.viewport()
        return ((pos[0] - ox) * LOGICAL_W / w, (pos[1] - oy) * LOGICAL_H / h)

    def handle_click(self, pos):
        if self.state == TITLE:
            self.handle_title_click(pos)
        elif self.state == PLAYING:
            if self.scroll:
                if self.scroll_t > 0.4:
                    self.scroll = None
            elif self.paused:
                if self.resume_button.clicked(pos):
                    self.paused = False
                elif self.quit_button.clicked(pos):
                    self.back_to_title()
        elif self.state == LEVEL_COMPLETE:
            if self.continue_button.clicked(pos):
                self.advance()
        elif self.state in (GAME_OVER, WIN):
            if self.retry_button.clicked(pos):
                self.sail_again()
            elif self.port_button.clicked(pos):
                self.audio.play("click")
                self.back_to_title()
        elif self.state == LEADERBOARD:
            if self.back_button.clicked(pos):
                self.audio.play("click")
                self.back_to_title()

    def sail_again(self):
        """Straight back to island one as the same pirate."""
        self.audio.play("bell")
        self.start_new_game(self.player_name, self.save_score)

    def advance(self):
        """Leave the island-cleared card."""
        if self.state_t < self.reveal_done_at():
            self.state_t = self.reveal_done_at()       # first press skips the tally
            return
        self.audio.play("click")
        if self.is_secret:
            self.finish_game(won=True)
        elif self.level_index + 1 < len(levels.LEVELS):
            self.load_level(self.level_index + 1)
        elif self.map_complete():
            self.load_level(len(levels.LEVELS))
        else:
            self.finish_game(won=True)

    def map_complete(self):
        return self.score.fragments >= len(levels.LEVELS)

    def reveal_done_at(self):
        return 0.5 + 0.38 * len(self.bonus_lines) + 0.3

    def finish_game(self, won):
        self.score.finish_run(won, self.lives)
        self.final_lines = self.score.breakdown()
        self.previous_best = data.best_score(self.scores, self.player_name)
        if self.save_score:
            self.scores = data.record_score(self.scores, self.player_name,
                                            self.score.total, self.score.summary())
            self.refresh_roster()
        if self.director:
            self.director.stop()
        self.audio.loop(audio.WEATHER, None)
        self.audio.loop(audio.MUSIC, "shanty" if won else None)
        self.audio.play(("secret" if self.score.legend else "win") if won else "over")
        self.mood = art.MOODS["title" if won else "night"]
        self.set_state(WIN if won else GAME_OVER)

    def complete_level(self):
        self.director.stop()
        self.audio.loop(audio.WEATHER, None)
        self.bonus_lines = self.score.finish_level(self.level_number, self.cfg["par"],
                                                   secret=self.is_secret)
        self.tally_shown = 0
        self.audio.play("secret" if self.is_secret else "clear")
        last = self.level_index + 1 == len(levels.LEVELS)
        if self.is_secret:
            self.continue_button.text = "Claim Glory"
        elif last and self.map_complete():
            self.continue_button.text = "To Skull Cove"
        else:
            self.continue_button.text = "Finish" if last else "Continue"
        self.set_state(LEVEL_COMPLETE)

    def get_keys(self):
        pressed = pygame.key.get_pressed()
        return {
            "left": pressed[pygame.K_LEFT] or pressed[pygame.K_a],
            "right": pressed[pygame.K_RIGHT] or pressed[pygame.K_d],
            "up": pressed[pygame.K_UP] or pressed[pygame.K_w],
            "down": pressed[pygame.K_DOWN] or pressed[pygame.K_s],
        }

    # ------------------------------------------------------------ digging
    def try_dig(self):
        if self.is_secret:
            self.toast("No shovel work here - the stones hold this island's secret.")
            return
        if self.dig_cool > 0:
            return
        tile = self.player_tile()
        if self.chest_found:
            self.toast("This island's chest is already yours.")
        elif tile in self.holes:
            self.toast("Ye've dug here already.")
        elif any((p.col, p.row) == tile for p in self.puddles):
            self.toast("Can't dig in a tide pool.")
        elif self.digs_left <= 0:
            self.toast("Yer shovel arm is spent - no digs left on this island.")
        else:
            self.dig(tile)

    def dig(self, tile):
        self.digs_left -= 1
        self.digs_used += 1
        self.dig_cool = 0.35
        self.holes.add(tile)
        cx = tile[0] * TILE_SIZE + TILE_SIZE // 2
        cy = tile[1] * TILE_SIZE + TILE_SIZE // 2
        art.draw_hole(self.island, cx + ISLAND_PAD, cy + ISLAND_PAD + 6)
        self.particles.burst(cx, cy + 6, (214, 180, 124), 12, 110, 0.5, 3,
                             colors=[(214, 180, 124), (190, 152, 98), (236, 206, 150)])
        self.audio.play("dig")
        if tile != self.plan["chest"]:
            left = self.digs_left
            self.toast(f"{treasure.warmth(tile, self.plan['chest'])}  "
                       f"({left} dig{'s' if left != 1 else ''} left)")
            return

        self.chest_found = True
        self.chest_t = 0.0
        self.score.fragments += 1
        self.audio.play("thud")
        self.audio.play("chest")
        self.shake.kick(5)
        self.particles.burst(cx, cy, GOLD, 30, 190, 0.9, 4,
                             colors=[GOLD, GOLD_LIT, (255, 255, 230)])
        value = scoring.CHEST_BASE + 50 * self.level_number
        self.award("treasure", value, "Buried treasure!", at=(cx, cy - 20))
        if self.digs_used == 1:
            bonus = scoring.FIRST_DIG_BONUS + 25 * self.level_number
            self.score.add("enigma", bonus)
            self.popup(f"+{bonus}  Riddle read true!", cx, cy - 62, (190, 240, 255), big=True)
        note = f"Map fragment {self.score.fragments} of {len(levels.LEVELS)}"
        if self.lives < MAX_LIVES:
            self.lives += 1
            note += " - and a flask of grog restores a life"
        self.announce("BURIED TREASURE!", note, (176, 122, 20))

    # -------------------------------------------------------------- runes
    def press_plate(self, tile):
        rune = self.plates[tile]
        order = self.runes["order"]
        if self.vault_open or rune in order[:self.rune_progress]:
            return
        x = tile[0] * TILE_SIZE + TILE_SIZE / 2
        y = tile[1] * TILE_SIZE + TILE_SIZE / 2
        if rune == order[self.rune_progress]:
            self.rune_progress += 1
            self.audio.play("rune_ok")
            self.particles.burst(x, y, art.RUNE_COLORS[rune], 16, 120, 0.7, 3, 0)
            if self.rune_progress == len(order):
                self.open_vault()
            else:
                self.toast(f"The stone glows. {len(order) - self.rune_progress} to go.")
            return
        self.rune_mistakes += 1
        self.rune_progress = 0
        self.rune_bad_t = 0.9
        self.audio.play("rune_bad")
        self.shake.kick(6)
        message = "Wrong stone! The plates go dark."
        if self.extra_crabs < 3:
            self.extra_crabs += 1
            far = max(self.sand_tiles, key=lambda s: (self.dist.get(s, 0), random.random()))
            self.monsters.append(Monster(far[0], far[1], self.monster_color,
                                         self.cfg["monster_speed"], "chase"))
            message += " Something stirs in the cove..."
        self.toast(message)

    def open_vault(self):
        self.vault_open = True
        doors = {(c * TILE_SIZE, r * TILE_SIZE) for c, r in self.vault_doors}
        self.wall_rects = [w for w in self.wall_rects if w.topleft not in doors]
        self.walk_tiles |= set(self.vault_doors)
        self.update_field(force=True)
        self.audio.play("vault")
        self.shake.kick(9)
        for c, r in self.vault_doors:
            self.particles.burst(c * TILE_SIZE + 20, r * TILE_SIZE + 20, (150, 160, 170),
                                 24, 150, 0.9, 4)
        bonus = scoring.RUNES_BONUS + (scoring.RUNES_CLEAN_BONUS if not self.rune_mistakes else 0)
        self.score.add("enigma", bonus)
        self.announce("THE VAULT OPENS!", f"+{bonus} for reading the stones"
                      + (" without a false step" if not self.rune_mistakes else ""),
                      (44, 92, 84))

    # -------------------------------------------------------------- update
    def hurt(self, sound="hit"):
        self.lives -= 1
        self.score.hit()
        self.player.start_invincibility()
        self.shake.kick(8)
        self.hurt_flash = 1.0
        self.audio.play(sound)
        self.particles.burst(self.player.x, self.player.y, (226, 75, 84), 14, 150, 0.5, 3)
        if self.lives <= 0:
            self.finish_game(won=False)
            return True
        return False

    def update_playing(self, dt):
        self.dig_cool = max(0.0, self.dig_cool - dt)
        self.rune_bad_t = max(0.0, self.rune_bad_t - dt)
        if self.chest_found:
            self.chest_t += dt
        self.score.tick(dt)

        player = self.player
        player.update(dt, self.get_keys(), self.wall_rects, self.bounds)
        wx, wy = self.director.wind_vector()
        if wx or wy:
            player.push(wx * dt, wy * dt, self.wall_rects, self.bounds)
        if player.moving and random.random() < dt * 9:
            self.particles.puff(player.x, player.y + 13)

        if self.update_field():
            tile = self.prev_tile
            if tile in self.plates:
                self.press_plate(tile)

        for coin in self.coins:
            coin.update(dt)
        for puddle in self.puddles:
            puddle.update(dt)
        for monster in self.monsters:
            monster.update(dt, player, self.wall_rects, self.bounds, self.dist)
        self.director.update(dt)

        storm = self.director.storm
        for coin in self.coins:
            if not coin.collected and math.hypot(coin.x - player.x, coin.y - player.y) \
                    < coin.radius + player.radius:
                coin.collected = True
                self.coins_collected_level += 1
                gained, mult, stepped = self.score.coin(storm, coin.value)
                self.audio.play(f"coin{mult}")
                self.particles.burst(coin.x, coin.y, GOLD_LIT, 7, 90, 0.4, 3,
                                     colors=[GOLD, GOLD_LIT])
                label = f"+{gained}"
                if storm:
                    label += " storm"
                self.popup(label, coin.x, coin.y - 16,
                           (150, 220, 255) if storm else GOLD_LIT)
                if stepped:
                    self.audio.play("combo")
                    self.popup(f"COMBO x{mult}!", player.x, player.y - 44,
                               (255, 150, 90), big=True)

        if not self.bottle_taken and self.plan:
            bx = self.plan["bottle"][0] * TILE_SIZE + TILE_SIZE / 2
            by = self.plan["bottle"][1] * TILE_SIZE + TILE_SIZE / 2
            if math.hypot(bx - player.x, by - player.y) < 22:
                self.bottle_taken = True
                self.clue = self.plan
                self.score.add("treasure", scoring.BOTTLE_VALUE)
                self.audio.play("bottle")
                self.open_scroll()

        if self.crown and self.vault_open:
            cx = self.crown[0] * TILE_SIZE + TILE_SIZE / 2
            cy = self.crown[1] * TILE_SIZE + TILE_SIZE / 2
            if math.hypot(cx - player.x, cy - player.y) < 24:
                self.score.add("secret", scoring.CROWN_VALUE)
                self.score.legend = True
                self.crown = None
                self.complete_level()
                return

        if not player.is_invincible:
            cause = None
            for puddle in self.puddles:
                if math.hypot(puddle.x - player.x, puddle.y - player.y) \
                        < puddle.radius + player.radius * 0.8:
                    cause = "splash"
                    break
            if not cause:
                for monster in self.monsters:
                    if math.hypot(monster.x - player.x, monster.y - player.y) \
                            < monster.radius + player.radius:
                        cause = "hit"
                        break
            if not cause:
                cause = self.director.hazard_hit(player)
            if cause and self.hurt(cause):
                return

        if not self.is_secret and self.total_coins > 0 \
                and self.coins_collected_level >= self.total_coins:
            self.complete_level()

    def update(self, dt):
        self.mouse = self.to_logical_pos(pygame.mouse.get_pos())
        self.time += dt
        self.state_t += dt
        self.sea_fx.update(dt)
        self.shake.update(dt)
        self.flash = max(0.0, self.flash - dt * 3.5)
        self.hurt_flash = max(0.0, self.hurt_flash - dt * 3.0)
        self.shown_score += (self.score.total - self.shown_score) * min(1.0, dt * 9)
        if self.score.total - self.shown_score < 1:
            self.shown_score = self.score.total

        if self.state == PLAYING:
            if self.scroll:
                self.scroll_t += dt
            elif not self.paused:
                self.update_playing(dt)
                self.particles.update(dt)
                if self.banner:
                    self.banner[3] += dt
                    if self.banner[3] > 3.4:
                        self.banner = None
                for t in self.toasts:
                    t[1] += dt
                self.toasts = [t for t in self.toasts if t[1] < 3.0]
                if self.director and self.director.storm:
                    self.rain.update(dt, self.director.wind_vector()[0])
        elif self.state == TITLE:
            self.name_field.update(dt)
        elif self.state == LEVEL_COMPLETE:
            self.particles.update(dt)
            shown = int(max(0.0, self.state_t - 0.5) / 0.38)
            shown = min(shown, len(self.bonus_lines))
            if shown > self.tally_shown:
                self.tally_shown = shown
                self.audio.play("tally")

    # ---------------------------------------------------------------- draw
    def draw_hud(self):
        s = self.surface
        mid = HUD_H // 2
        s.blit(self.hud_band, (0, 0))
        pygame.draw.line(s, (136, 98, 60), (0, 1), (LOGICAL_W, 1), 2)
        pygame.draw.line(s, HUD_EDGE, (0, HUD_H - 2), (LOGICAL_W, HUD_H - 2), 4)

        def caption(text, x, align="left", color=HUD_DIM):
            cap = self.font_label.render(text, True, color)
            rect = cap.get_rect(top=7)
            setattr(rect, "left" if align == "left" else "right", x)
            s.blit(cap, rect)

        x = 16
        # Island
        caption("COVE" if self.is_secret else "ISLAND", x)
        if self.is_secret:
            num = self.font_hud.render("???", True, (150, 236, 200))
            s.blit(num, (x, 24))
            x += max(num.get_width(), 46) + 16
        else:
            num = self.font_hud.render(str(self.level_number), True, HUD_TEXT)
            den = self.font_small.render(f"/{len(levels.LEVELS)}", True, HUD_DIM)
            s.blit(num, (x, 24))
            s.blit(den, (x + num.get_width() + 1, 28))
            x += 46 + 14

        # Lives
        caption("LIVES", x)
        for i in range(MAX_LIVES):
            draw_heart(s, x + 11 + i * 25, 37, 21, filled=i < self.lives)
        x += MAX_LIVES * 25 + 14

        # Coins: the count plus how much of the island is left
        caption("COINS", x)
        found = self.font_hud.render(str(self.coins_collected_level), True, GOLD_LIT)
        total = self.font_small.render(f"/{self.total_coins}", True, HUD_DIM)
        s.blit(found, (x, 22))
        s.blit(total, (x + found.get_width() + 1, 26))
        track = pygame.Rect(x, 47, 70, 5)
        pygame.draw.rect(s, (34, 22, 14), track, border_radius=3)
        if self.total_coins:
            filled = int(track.width * self.coins_collected_level / self.total_coins)
            if filled > 0:
                pygame.draw.rect(s, GOLD_LIT, (track.x, track.y, filled, track.height),
                                 border_radius=3)
        x += 70 + 16

        # Shovel digs / map fragments
        if not self.is_secret:
            caption("DIGS", x)
            for i in range(DIGS_PER_ISLAND):
                art.draw_shovel(s, x + 10 + i * 21, 37, lit=i < self.digs_left)
            x += DIGS_PER_ISLAND * 21 + 14
        caption("MAP", x)
        for i in range(len(levels.LEVELS)):
            art.draw_fragment(s, x + 9 + i * 21, 38, i, i < self.score.fragments, 8)
        x += len(levels.LEVELS) * 21 + 14

        # Clock against par
        par = self.cfg["par"]
        left = par - self.score.level_time
        caption("TIME", x)
        secs = int(self.score.level_time)
        clock = self.font_hud.render(f"{secs // 60}:{secs % 60:02d}", True,
                                     HUD_TEXT if left > 0 else (224, 130, 110))
        s.blit(clock, (x, 24))
        track = pygame.Rect(x, 47, 50, 5)
        pygame.draw.rect(s, (34, 22, 14), track, border_radius=3)
        if left > 0:
            pygame.draw.rect(s, (130, 200, 150),
                             (track.x, track.y, int(track.width * left / par), 5), border_radius=3)
        x += 50 + 16

        # Combo
        mult = self.score.multiplier
        caption("COMBO", x)
        live = self.score.chain > 0
        col = (255, 150, 90) if mult > 1 else (HUD_TEXT if live else HUD_DIM)
        label = self.font_hud.render(f"x{mult}", True, col)
        if mult > 1:
            k = 1.0 + 0.12 * math.sin(self.time * 12)
            label = pygame.transform.rotozoom(label, 0, k)
        s.blit(label, label.get_rect(midleft=(x, 34)))
        if live:
            chain = self.font_label.render(f"chain {self.score.chain}", True, HUD_DIM)
            s.blit(chain, (x + 34, 28))
        track = pygame.Rect(x, 47, 76, 5)
        pygame.draw.rect(s, (34, 22, 14), track, border_radius=3)
        if live:
            pygame.draw.rect(s, col, (track.x, track.y,
                                      int(track.width * self.score.chain_left), 5),
                             border_radius=3)

        # Right edge: the pirate and the plunder
        rx = LOGICAL_W - 16
        name = (self.player_name or "").upper()
        caption(f"{name}'S PLUNDER" if name else "PLUNDER", rx, "right")
        val = art.outlined(self.font_med, f"{int(self.shown_score):,}", GOLD_LIT, (40, 24, 10), 1)
        s.blit(val, val.get_rect(topright=(rx, 21)))
        if self.audio.muted:
            mute = self.font_label.render("MUTED", True, (224, 130, 110))
            s.blit(mute, mute.get_rect(topright=(rx - val.get_width() - 10, 36)))

    def draw_world(self):
        s = self.surface
        ox, oy = self.ox, self.oy
        s.blit(self.sea(self.cfg["mood"]), (0, 0))
        self.sea_fx.draw_glints(s, self.mood["glint"], top=HUD_H)
        # Surf lapping at the beach.
        k = 0.5 + 0.5 * math.sin(self.time * 1.6)
        ring = pygame.Rect(ox, oy, self.grid_px_w, self.grid_px_h).inflate(int(16 + 10 * k),
                                                                           int(16 + 10 * k))
        pygame.draw.rect(s, self.mood["glint"], ring, 2, border_radius=30)
        s.blit(self.island, (ox - ISLAND_PAD, oy - ISLAND_PAD))

        for puddle in self.puddles:
            puddle.draw(s, ox, oy)
        self.director.draw_under(s, ox, oy)

        for tile, rune in self.plates.items():
            if self.rune_bad_t > 0 and int(self.rune_bad_t * 10) % 2:
                state = "bad"
            elif self.vault_open or rune in self.runes["order"][:self.rune_progress]:
                state = "lit"
            else:
                state = "idle"
            art.draw_rune_plate(s, rune, tile[0] * TILE_SIZE + 20 + ox,
                                tile[1] * TILE_SIZE + 20 + oy, state, self.time)
        if not self.vault_open:
            for c, r in self.vault_doors:
                art.draw_vault_door(s, c * TILE_SIZE + ox, r * TILE_SIZE + oy, self.time)

        if self.plan:
            if not self.bottle_taken:
                c, r = self.plan["bottle"]
                art.draw_bottle(s, c * TILE_SIZE + 20 + ox, r * TILE_SIZE + 20 + oy, self.time)
            if self.chest_found:
                c, r = self.plan["chest"]
                art.draw_chest(s, c * TILE_SIZE + 20 + ox, r * TILE_SIZE + 22 + oy,
                               min(1.0, self.chest_t / 0.5))
        for coin in self.coins:
            coin.draw(s, ox, oy)
        if self.crown:
            art.draw_crown(s, self.crown[0] * TILE_SIZE + 20 + ox,
                           self.crown[1] * TILE_SIZE + 20 + oy, self.time)
        for monster in self.monsters:
            monster.draw(s, ox, oy)
        self.player.draw(s, ox, oy)
        self.director.draw_over(s, ox, oy)
        self.particles.draw(s, ox, oy)

        # Light: lantern at night, storm gloom, lightning, the sting of a hit.
        play = pygame.Rect(0, HUD_H, LOGICAL_W, LOGICAL_H - HUD_H)
        if self.light:
            s.set_clip(play)
            lw, lh = self.light.get_size()
            s.blit(self.light, (int(self.player.x + ox - lw // 2),
                                int(self.player.y + oy - lh // 2)),
                   special_flags=pygame.BLEND_RGB_MULT)
            s.set_clip(None)
        gloom = self.director.storm_strength()
        if self.light:
            gloom *= 0.4          # the night is dark enough already
        if gloom > 0:
            col = tuple(int(255 - (255 - c) * gloom) for c in (150, 162, 192))
            s.fill(col, play, special_flags=pygame.BLEND_RGB_MULT)
            self.rain.draw(s, self.director.wind_vector()[0], self.director.storm_strength())
        if self.flash > 0.02:
            v = int(110 * self.flash)
            s.fill((v, v, int(v * 1.1)), play, special_flags=pygame.BLEND_RGB_ADD)
        if self.hurt_flash > 0.02:
            s.fill((int(90 * self.hurt_flash), 0, 0), play, special_flags=pygame.BLEND_RGB_ADD)
        self.sea_fx.draw_gulls(s)

    def draw_playing(self, overlays=True):
        self.draw_world()
        self.draw_hud()
        if not overlays:
            return
        s = self.surface
        if self.banner and not self.scroll:
            text, sub, color, t = self.banner
            k = min(1.0, t / 0.25, (3.4 - t) / 0.4)
            y = HUD_H + 34 - int((1 - k) * 60)
            art.ribbon(s, self.font_med, text, LOGICAL_W // 2, y, fill=color)
            if sub:
                note = art.outlined(self.font_small, sub, (255, 244, 214), (30, 20, 12), 1)
                s.blit(note, note.get_rect(center=(LOGICAL_W // 2, y + 34)))
        for text, t in self.toasts:
            label = self.font_small.render(text, True, (255, 244, 214))
            box = label.get_rect(center=(LOGICAL_W // 2, LOGICAL_H - 26)).inflate(28, 12)
            pygame.draw.rect(s, (40, 26, 16), box, border_radius=10)
            pygame.draw.rect(s, (150, 112, 62), box, 2, border_radius=10)
            s.blit(label, label.get_rect(center=box.center))
        if self.scroll:
            self.draw_scroll()
        elif self.paused:
            self.draw_pause()

    def dim(self, amount=110):
        self.surface.fill((amount, amount, amount), special_flags=pygame.BLEND_RGB_MULT)

    def draw_scroll(self):
        s = self.surface
        self.dim(96)
        w, h = 640, 400
        k = min(1.0, self.scroll_t / 0.18)
        x, y = (LOGICAL_W - w) // 2, (LOGICAL_H - h) // 2 + 14 + int((1 - k) * 30)
        s.blit(art.parchment(w, h, 2), (x, y))
        title = art.outlined(self.font_med, self.scroll["title"], art.BLOOD, (255, 240, 210), 1)
        s.blit(title, title.get_rect(center=(LOGICAL_W // 2, y + 44)))
        pygame.draw.line(s, art.PARCHMENT_EDGE, (x + 90, y + 68), (x + w - 90, y + 68), 2)

        cy = y + 90
        for style, text in self.scroll["lines"]:
            if style == "cipher":
                font, color, lead = self.font_med, (120, 30, 28), 30
            elif style == "hint":
                font, color, lead = self.font_tiny, INK_LABEL, 20
                cy += 8
            else:
                font, color, lead = self.font_small, INK, 26
            for line in art.wrap(font, text, w - 110):
                label = font.render(line, True, color)
                s.blit(label, label.get_rect(center=(LOGICAL_W // 2, cy)))
                cy += lead
            cy += 8
        foot = self.font_tiny.render("SPACE rolls it up  -  C reads it again", True, INK_SOFT)
        s.blit(foot, foot.get_rect(center=(LOGICAL_W // 2, y + h - 30)))

    def draw_pause(self):
        s = self.surface
        self.dim(96)
        s.blit(art.parchment(380, 330, 5), (260, 150))
        title = art.outlined(self.font_big, "Ahoy!", art.BLOOD, (255, 240, 210), 2)
        s.blit(title, title.get_rect(center=(LOGICAL_W // 2, 212)))
        note = self.font_small.render("The voyage waits for ye.", True, INK_SOFT)
        s.blit(note, note.get_rect(center=(LOGICAL_W // 2, 252)))
        self.resume_button.draw(s, self.font_med, self.mouse)
        self.quit_button.draw(s, self.font_small, self.mouse)
        keys = self.font_tiny.render("SPACE dig   C clue   M sound   P pause", True, INK_LABEL)
        s.blit(keys, keys.get_rect(center=(LOGICAL_W // 2, 430)))

    def draw_backdrop(self, mood_name):
        s = self.surface
        s.blit(self.sea(mood_name), (0, 0))
        self.sea_fx.draw_glints(s, art.MOODS[mood_name]["glint"], top=170)

    def draw_ship(self, cx, cy, scale=1.0, color=(30, 22, 30)):
        """A far-off silhouette on the horizon."""
        s = self.surface
        bob = math.sin(self.time * 1.1) * 2
        cy = cy + bob
        k = scale
        pygame.draw.polygon(s, color, [(cx - 46 * k, cy), (cx + 50 * k, cy), (cx + 38 * k, cy + 14 * k),
                                       (cx - 34 * k, cy + 14 * k)])
        for mx, top, wide in ((-16, 58, 22), (14, 70, 26)):
            pygame.draw.line(s, color, (cx + mx * k, cy), (cx + mx * k, cy - top * k), max(1, int(3 * k)))
            pygame.draw.polygon(s, color, [(cx + mx * k + 2, cy - top * k + 4),
                                           (cx + (mx + wide) * k, cy - top * k * 0.55),
                                           (cx + mx * k + 2, cy - 8 * k)])
        pygame.draw.polygon(s, color, [(cx + 14 * k, cy - 70 * k), (cx + 28 * k, cy - 74 * k),
                                       (cx + 14 * k, cy - 78 * k)])

    def draw_title(self):
        s = self.surface
        self.draw_backdrop("title")
        # Low sun on the horizon, and a ship crossing it.
        pygame.draw.circle(s, (255, 214, 140), (690, 132), 44)
        pygame.draw.circle(s, (255, 236, 190), (690, 132), 34)
        pygame.draw.rect(s, (70, 110, 150), (0, 136, LOGICAL_W, 12))
        s.blit(self.sea("title"), (0, 140), (0, 140, LOGICAL_W, 40))
        self.draw_ship(214 + math.sin(self.time * 0.07) * 14, 128, 0.7)
        self.sea_fx.draw_gulls(s)

        art.skull_and_bones(s, 118, 62, 1.25)
        art.skull_and_bones(s, LOGICAL_W - 118, 62, 1.25)
        s.blit(self.title_art, self.title_art.get_rect(center=(LOGICAL_W // 2, 52)))
        sub = art.outlined(self.font_med, "T R E A S U R E   H U N T", (255, 240, 210), (60, 24, 16), 2)
        s.blit(sub, sub.get_rect(center=(LOGICAL_W // 2, 104)))

        self.draw_best_banner(140)

        s.blit(art.parchment(716, 312, 1), (92, 164))

        # Two ways aboard, side by side, split by an OR rule.
        head_left = self.font_med.render("Returning pirate", True, INK)
        s.blit(head_left, head_left.get_rect(midleft=(125, 198)))
        head_right = self.font_med.render("New pirate", True, INK)
        s.blit(head_right, head_right.get_rect(midleft=(475, 198)))

        pygame.draw.line(s, (204, 180, 132), (450, 190), (450, 440), 2)
        or_chip = pygame.Rect(0, 0, 40, 28)
        or_chip.center = (450, 300)
        pygame.draw.rect(s, art.PARCHMENT_LIT, or_chip, border_radius=8)
        or_label = self.font_small.render("or", True, INK_LABEL)
        s.blit(or_label, or_label.get_rect(center=or_chip.center))

        typing = self.typing_new_name()
        self.combo.draw(s, self.font_med, self.font_small, active=not typing)
        self.name_field.draw(s, self.font_med, active=True)
        self.save_checkbox.draw(s, self.font_small, active=typing)

        # Under each column, say what will actually happen.
        if typing:
            typed = data.clean_name(self.name_field.text)
            match = data.find_player(self.scores, typed)
            if match:
                hint = f"Joins {match} (best {data.best_score(self.scores, match)})"
                color = GOOD
            elif self.save_checkbox.checked:
                hint = "New pirate - will join the roster"
                color = INK_LABEL
            else:
                hint = "Guest run - nothing will be saved"
                color = BAD
            note = self.font_small.render(hint, True, color)
            s.blit(note, note.get_rect(midleft=(475, 336)))
        else:
            note = self.font_small.render(
                f"{len(self.combo.items)} pirate(s) registered", True, INK_LABEL)
            s.blit(note, note.get_rect(midleft=(125, 292)))

        # What the voyage holds, in the panel's spare room.
        tips = ["Chain coins for combos.", "Read the bottle, dig for the chest.",
                "Five map fragments... and then?"]
        for i, tip in enumerate(tips):
            label = self.font_tiny.render(tip, True, INK_SOFT)
            s.blit(label, (139, 330 + i * 24))
            pygame.draw.circle(s, GOLD_DEEP, (129, 337 + i * 24), 3)
        keys = self.font_tiny.render(
            "Arrows / WASD move   SPACE dig   C clue   P pause   M sound", True, INK_SOFT)
        s.blit(keys, keys.get_rect(center=(LOGICAL_W // 2, 452)))

        self.play_button.enabled = bool(self.chosen_name())
        self.play_button.draw(s, self.font_med, self.mouse)
        self.fame_button.draw(s, self.font_med, self.mouse)

        hint = self.font_small.render("Enter to set sail", True, (226, 240, 248))
        s.blit(hint, hint.get_rect(center=(LOGICAL_W // 2, 574)))

        # Last, so the open list floats over the panel and the button.
        self.combo.draw_list(s, self.font_small, self.mouse)

    def draw_best_banner(self, cy):
        best = self.scores["overall_best"]
        if best["name"]:
            text = f"Best pirate: {best['name']} - {best['score']:,} points"
        else:
            text = "No treasure claimed yet - be the first!"
        label = self.font_small.render(text, True, INK)
        chip = label.get_rect(center=(LOGICAL_W // 2, cy)).inflate(84, 12)
        ui.shadowed_box(self.surface, chip, (255, 233, 176), radius=chip.height // 2,
                        edge=GOLD_DEEP, width=2)
        self.surface.blit(self.coin_icon,
                          self.coin_icon.get_rect(midleft=(chip.x + 10, cy)))
        self.surface.blit(label, label.get_rect(center=(LOGICAL_W // 2 + 8, cy)))

    def draw_fragments_row(self, cx, y, size=13, gap=34):
        n = len(levels.LEVELS)
        x0 = cx - (n - 1) * gap // 2
        for i in range(n):
            art.draw_fragment(self.surface, x0 + i * gap, y, i, i < self.score.fragments, size)

    def draw_level_complete(self):
        self.draw_playing(overlays=False)
        s = self.surface
        self.dim(120)
        self.particles.draw(s, self.ox, self.oy)

        w, h = 560, 470
        x, y = (LOGICAL_W - w) // 2, 78
        s.blit(art.parchment(w, h, 3), (x, y))
        heading = "The Dread Crown is Yours!" if self.is_secret else "Island Cleared!"
        title = art.outlined(self.font_big, heading, GOOD, (255, 244, 214), 2)
        if title.get_width() > w - 40:
            title = art.outlined(self.font_med, heading, GOOD, (255, 244, 214), 2)
        s.blit(title, title.get_rect(center=(LOGICAL_W // 2, y + 50)))
        sub = self.font_small.render(self.cfg["name"], True, INK_SOFT)
        s.blit(sub, sub.get_rect(center=(LOGICAL_W // 2, y + 86)))

        ly = y + 116
        for i, (label, points) in enumerate(self.bonus_lines[:self.tally_shown]):
            left = self.font_small.render(label, True, INK)
            right = self.font_small.render(f"+{points:,}", True, GOLD_DEEP)
            s.blit(left, (x + 70, ly))
            s.blit(right, right.get_rect(topright=(x + w - 70, ly)))
            pygame.draw.line(s, (214, 190, 140), (x + 70, ly + 22), (x + w - 70, ly + 22), 1)
            ly += 28
        done = self.state_t >= self.reveal_done_at()
        if done:
            total = art.outlined(self.font_med, f"Plunder so far: {self.score.total:,}",
                                 GOLD_LIT, (60, 34, 10), 2)
            s.blit(total, total.get_rect(center=(LOGICAL_W // 2, y + 292)))

            for i in range(MAX_LIVES):
                draw_heart(s, LOGICAL_W // 2 - 26 + i * 26, y + 326, 20, filled=i < self.lives)

            self.draw_fragments_row(LOGICAL_W // 2, y + 362)
            last = self.level_index + 1 == len(levels.LEVELS)
            if self.is_secret:
                note, color = "The legend of the islands is complete.", GOOD
            elif self.map_complete():
                note = ("The map is whole - and it shows a sixth island!" if last
                        else "The map is whole. Clear the islands to follow it.")
                color = art.BLOOD
            elif not self.chest_found:
                note, color = "This island's chest stayed buried. The map has a hole in it.", BAD
            else:
                note = f"Map fragment found: {self.score.fragments} of {len(levels.LEVELS)}"
                color = INK_SOFT
            label = self.font_tiny.render(note, True, color)
            s.blit(label, label.get_rect(center=(LOGICAL_W // 2, y + 392)))
            self.continue_button.rect.center = (LOGICAL_W // 2, y + 430)
            self.continue_button.draw(s, self.font_med, self.mouse)

    def draw_end_screen(self, won):
        s = self.surface
        legend = self.score.legend
        self.draw_backdrop("title" if won else "night")
        self.sea_fx.draw_gulls(s)

        if legend:
            heading, color = "Pirate Legend!", GOLD_LIT
            sub_text = "Ye read the map, woke the vault and took the Dread Crown."
        elif won:
            heading, color = "You win, matey!", (150, 230, 150)
            if self.map_complete():
                sub_text = "Every island plundered."
            else:
                sub_text = (f"Every island plundered - but the old map is unfinished "
                            f"({self.score.fragments} of {len(levels.LEVELS)} pieces).")
        else:
            heading, color = "Lost at Sea", (230, 120, 110)
            sub_text = "Better luck next time, sailor. Take a breath and sail again!"
        title = art.outlined(self.font_big, heading, color, (30, 18, 12), 3)
        s.blit(title, title.get_rect(center=(LOGICAL_W // 2, 40)))
        sub = art.outlined(self.font_small, sub_text, (255, 244, 214), (30, 18, 12), 1)
        s.blit(sub, sub.get_rect(center=(LOGICAL_W // 2, 82)))

        # Left: where the score came from.
        px, py, pw, ph = 40, 104, 430, 420
        s.blit(art.parchment(pw, ph, 7), (px, py))
        rank = scoring.rank_for(self.score.total, legend)
        head = self.font_med.render(f"{self.player_name}", True, INK)
        s.blit(head, (px + 36, py + 28))
        chip = self.font_small.render(rank, True, (255, 244, 214))
        box = chip.get_rect(topright=(px + pw - 40, py + 30)).inflate(20, 10)
        pygame.draw.rect(s, art.BLOOD if not legend else GOLD_DEEP, box, border_radius=9)
        s.blit(chip, chip.get_rect(center=box.center))

        ly = py + 70
        for label, points in self.final_lines:
            left = self.font_small.render(label, True, INK)
            right = self.font_small.render(f"{points:,}", True, GOLD_DEEP)
            s.blit(left, (px + 38, ly))
            s.blit(right, right.get_rect(topright=(px + pw - 40, ly)))
            pygame.draw.line(s, (214, 190, 140), (px + 38, ly + 20), (px + pw - 40, ly + 20), 1)
            ly += 24
        if not self.final_lines:
            none = self.font_small.render("Not a single doubloon.", True, INK_SOFT)
            s.blit(none, (px + 38, ly))
        pygame.draw.line(s, INK_SOFT, (px + 38, py + ph - 92), (px + pw - 40, py + ph - 92), 2)
        total_cap = self.font_med.render("Final plunder", True, INK)
        s.blit(total_cap, (px + 38, py + ph - 82))
        total = art.outlined(self.font_med, f"{self.score.total:,}", GOLD_LIT, (60, 34, 10), 2)
        s.blit(total, total.get_rect(topright=(px + pw - 38, py + ph - 86)))

        if self.save_score:
            best = data.best_score(self.scores, self.player_name)
            if self.score.total > self.previous_best:
                note, col = "A new personal record!", GOOD
            else:
                note, col = f"Your best: {best:,}", INK_SOFT
        else:
            note, col = "Guest run - this score was not saved", BAD
        label = self.font_small.render(note, True, col)
        s.blit(label, (px + 38, py + ph - 48))
        info = self.font_tiny.render(
            f"Longest chain x{self.score.best_chain}", True, INK_LABEL)
        s.blit(info, info.get_rect(topright=(px + pw - 40, py + ph - 44)))

        # Right: the roster, and the old map.
        self.draw_leaderboard_panel(490, 104, 370, 250)
        s.blit(art.parchment(370, 158, 9), (490, 366))
        cap = self.font_small.render("The old map", True, INK)
        s.blit(cap, cap.get_rect(center=(675, 396)))
        self.draw_fragments_row(675, 434, 15, 42)
        if legend:
            hint = "Whole at last. It led ye true."
        elif self.map_complete():
            hint = "Whole! Clear every island to follow it."
        else:
            hint = "Each island buries one piece. All five show the way to..."
        for i, line in enumerate(art.wrap(self.font_tiny, hint, 300)):
            label = self.font_tiny.render(line, True, INK_SOFT)
            s.blit(label, label.get_rect(center=(675, 468 + i * 18)))

        self.retry_button.draw(s, self.font_med, self.mouse)
        self.port_button.draw(s, self.font_med, self.mouse)

    def draw_leaderboard_panel(self, x, y, w, h, rows=6):
        """Top few pirates, plus the current one pinned on if they ranked lower."""
        s = self.surface
        ranking = data.ranking(self.scores)
        shown = ranking[:rows]
        if self.save_score and self.player_name and \
                self.player_name not in [n for n, _ in shown]:
            place = next((i for i, (n, _) in enumerate(ranking)
                          if n == self.player_name), None)
            if place is not None:
                shown = shown[:rows - 1] + [ranking[place]]

        s.blit(art.parchment(w, h, 8), (x, y))
        header = self.font_small.render("Leaderboard - best voyages", True, INK)
        s.blit(header, header.get_rect(center=(x + w // 2, y + 34)))
        pygame.draw.line(s, art.PARCHMENT_EDGE, (x + 40, y + 52), (x + w - 40, y + 52), 2)

        if not shown:
            empty = self.font_small.render("No saved scores yet.", True, INK_LABEL)
            s.blit(empty, (x + 36, y + 66))
            return

        for i, (name, best) in enumerate(shown):
            place = next(j for j, (n, _) in enumerate(ranking) if n == name)
            highlight = self.save_score and name == self.player_name
            color = art.BLOOD if highlight else INK
            ry = y + 64 + i * 27
            if highlight:
                pygame.draw.rect(s, (250, 226, 168), (x + 28, ry - 4, w - 56, 25), border_radius=7)
            label = self.font_small.render(f"{place + 1}.  {name}", True, color)
            s.blit(label, (x + 38, ry))
            if data.is_legend(self.scores, name):
                art.draw_rune_glyph(s, "star", x + 46 + label.get_width() + 6, ry + 8,
                                    GOLD_DEEP, 0.7)
            value = self.font_small.render(f"{best:,}", True, color)
            s.blit(value, value.get_rect(topright=(x + w - 38, ry)))

    def draw_hall_of_fame(self):
        s = self.surface
        self.draw_backdrop("title")
        self.sea_fx.draw_gulls(s)
        title = art.outlined(self.font_big, "Hall of Fame", GOLD_LIT, (40, 22, 10), 3)
        s.blit(title, title.get_rect(center=(LOGICAL_W // 2, 44)))

        x, y, w, h = 90, 84, 720, 436
        s.blit(art.parchment(w, h, 4), (x, y))
        cols = [(x + 44, "#"), (x + 84, "Pirate"), (x + 290, "Rank"),
                (x + 478, "Isles"), (x + 546, "Map")]
        for cx, text in cols:
            s.blit(self.font_tiny.render(text.upper(), True, INK_LABEL), (cx, y + 30))
        cap = self.font_tiny.render("PLUNDER", True, INK_LABEL)
        s.blit(cap, cap.get_rect(topright=(x + w - 46, y + 30)))
        pygame.draw.line(s, art.PARCHMENT_EDGE, (x + 40, y + 50), (x + w - 40, y + 50), 2)

        runs = self.scores["runs"]
        if runs:
            for i, run in enumerate(runs[:data.MAX_RUNS]):
                ry = y + 60 + i * 30
                color = art.BLOOD if i == 0 else INK
                s.blit(self.font_small.render(str(i + 1), True, INK_LABEL), (x + 44, ry))
                s.blit(self.font_small.render(run["name"], True, color), (x + 84, ry))
                s.blit(self.font_small.render(
                    run["rank"] or scoring.rank_for(run["score"], run["legend"]),
                    True, GOLD_DEEP if run["legend"] else INK_SOFT), (x + 290, ry))
                s.blit(self.font_small.render(str(run["islands"]), True, INK_SOFT), (x + 488, ry))
                s.blit(self.font_small.render(f"{run['fragments']}/5", True, INK_SOFT),
                       (x + 546, ry))
                value = self.font_small.render(f"{run['score']:,}", True, color)
                s.blit(value, value.get_rect(topright=(x + w - 46, ry)))
                if run["legend"]:
                    art.draw_rune_glyph(s, "star", x + 66, ry + 8, GOLD_DEEP, 0.7)
        else:
            # Rosters from before voyages were logged still have their bests.
            ranking = data.ranking(self.scores)
            lines = ["No voyages logged yet. Set sail and claim the first line."]
            if ranking:
                lines.append("Bests carried over from the old roster:")
            for i, text in enumerate(lines):
                label = self.font_small.render(text, True, INK_SOFT)
                s.blit(label, label.get_rect(center=(LOGICAL_W // 2, y + 84 + i * 30)))
            for i, (name, best) in enumerate(ranking[:8]):
                ry = y + 150 + i * 30
                s.blit(self.font_small.render(f"{i + 1}.  {name}", True, INK), (x + 220, ry))
                value = self.font_small.render(f"{best:,}", True, GOLD_DEEP)
                s.blit(value, value.get_rect(topright=(x + w - 220, ry)))
        self.back_button.draw(s, self.font_med, self.mouse)

    def draw(self):
        if self.state == TITLE:
            self.draw_title()
        elif self.state == PLAYING:
            self.draw_playing()
        elif self.state == LEVEL_COMPLETE:
            self.draw_level_complete()
        elif self.state == WIN:
            self.draw_end_screen(won=True)
        elif self.state == GAME_OVER:
            self.draw_end_screen(won=False)
        elif self.state == LEADERBOARD:
            self.draw_hall_of_fame()

        # A quick fade up from black whenever the screen changes.
        if self.state_t < 0.3 and self.state != LEVEL_COMPLETE:
            v = int(255 * self.state_t / 0.3)
            self.surface.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)

        ox, oy, w, h = self.viewport()
        sx, sy = self.shake.offset()
        if (ox, oy) != (0, 0) or sx or sy:
            self.window.fill((8, 20, 34))
        # smoothscale costs tens of milliseconds per frame in WebAssembly,
        # which starves input; plain scale is nearest-neighbour but cheap.
        if (w, h) == (LOGICAL_W, LOGICAL_H):
            self.window.blit(self.surface, (ox + sx, oy + sy))
        else:
            resize = pygame.transform.scale if data.IS_WEB else pygame.transform.smoothscale
            k = w / LOGICAL_W
            self.window.blit(resize(self.surface, (w, h)), (ox + int(sx * k), oy + int(sy * k)))
        pygame.display.flip()

    # ----------------------------------------------------------------- run
    async def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)
            self.handle_events()
            if not self.running:
                break
            self.update(dt)
            self.draw()
            # Hands the frame back to the browser's event loop; a no-op on desktop.
            await asyncio.sleep(0)
        pygame.quit()

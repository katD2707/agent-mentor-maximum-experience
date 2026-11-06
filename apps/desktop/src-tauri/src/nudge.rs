//! Proactive nudges forwarded by the panel page (`desktop_nudge`): validation, the one-at-a-time
//! queue, where a nudge goes (speech balloon, Windows toast, nowhere) and where the balloon sits.
//! Everything here is pure so it can be unit tested; the window work lives in `main.rs`.

use std::collections::VecDeque;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{circle, fit, px, Rect, EDGE_MARGIN};

/// At most this many buttons (CONTRACTS.md section 9).
pub const MAX_ACTIONS: usize = 3;
/// Nudges waiting behind the one on screen; the oldest is dropped beyond that.
pub const MAX_PENDING: usize = 4;
/// Ids remembered after they were shown, so a replayed nudge (WebSocket reconnect) is not shown twice.
const RECENT: usize = 32;

const MAX_ID: usize = 128;
const MAX_TITLE: usize = 120;
const MAX_BODY: usize = 400;
const MAX_LABEL: usize = 40; // N: labels ≤40

/// Logical size of the balloon window. The card inside leaves room for its shadow and, on the side
/// of the bubble, for the tail (see `balloon.css`).
pub const BALLOON_W: f64 = 304.0;
pub const BALLOON_MIN_H: f64 = 96.0;
pub const BALLOON_MAX_H: f64 = 340.0;
/// Gap between the balloon window and the bubble's tile (the tail spans it visually).
pub const BALLOON_GAP: f64 = 2.0;
/// Where the tail points, measured from the top (bubble in the upper half) or from the bottom
/// (lower half) of the balloon window. Clamped so the tail stays on the card's straight edge.
const TAIL_FROM_END: f64 = 46.0;
const TAIL_MIN: f64 = 34.0;

pub const MASCOT_STATES: &[&str] = &[
    "idle",
    "listening",
    "thinking",
    "talking",
    "happy",
    "celebrate",
    "sleepy",
    "calm",
    "wave",
];
const KINDS: &[&str] = &[
    "checkin",
    "deadline",
    "review",
    "focus_end",
    "celebration",
    "report",
    "nudge",
];

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct NudgeAction {
    pub id: String,
    pub label: String,
}

/// A validated nudge. `id` keeps the JSON value the page sent (string or integer) so the
/// `mentor://nudge-action` event hands it back unchanged.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Nudge {
    pub id: Value,
    pub kind: String,
    pub title: String,
    pub body: String,
    pub actions: Vec<NudgeAction>,
    pub mascot: String,
}

fn clip(s: &str, max: usize) -> String {
    let s = s.split_whitespace().collect::<Vec<_>>().join(" ");
    if s.chars().count() <= max {
        return s;
    }
    let mut out: String = s.chars().take(max - 1).collect();
    out = out.trim_end().to_owned();
    out.push('…');
    out
}

/// Keeps line breaks in the body (paragraphs), collapses other runs of whitespace.
fn clip_body(s: &str, max: usize) -> String {
    let lines: Vec<String> = s
        .lines()
        .map(|l| l.split_whitespace().collect::<Vec<_>>().join(" "))
        .collect();
    let joined = lines.join("\n");
    let joined = joined.trim();
    if joined.chars().count() <= max {
        return joined.to_owned();
    }
    let mut out: String = joined.chars().take(max - 1).collect();
    out = out.trim_end().to_owned();
    out.push('…');
    out
}

/// `open`, `snooze_1h`, `done`, `start_focus`, `answer:<x>`: a lowercase word, optionally `:` and
/// a short value without control characters.
pub fn valid_action_id(id: &str) -> bool {
    let (word, value) = match id.split_once(':') {
        Some((w, v)) => (w, Some(v)),
        None => (id, None),
    };
    let word_ok = !word.is_empty()
        && word.len() <= 32
        && word
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_');
    let value_ok = value.is_none_or(|v| {
        !v.is_empty() && v.chars().count() <= 64 && !v.chars().any(char::is_control)
    });
    word_ok && value_ok
}

impl Nudge {
    /// Checks and normalizes what the page sent. Text is clipped, not refused; unknown kinds become
    /// `nudge`, unknown mascot states `happy`; invalid or duplicate actions are dropped.
    pub fn new(
        id: Value,
        kind: Option<String>,
        title: Option<String>,
        body: Option<String>,
        actions: Option<Vec<NudgeAction>>,
        mascot: Option<String>,
    ) -> Result<Nudge, String> {
        let id_ok = match &id {
            Value::String(s) => {
                !s.trim().is_empty()
                    && s.chars().count() <= MAX_ID
                    && !s.chars().any(char::is_control)
            }
            Value::Number(n) => n.is_i64() || n.is_u64(),
            _ => false,
        };
        if !id_ok {
            return Err("id must be a non-empty string (≤128 chars) or an integer".into());
        }
        let title = clip(title.as_deref().unwrap_or_default(), MAX_TITLE);
        let body = clip_body(body.as_deref().unwrap_or_default(), MAX_BODY);
        if title.is_empty() && body.is_empty() {
            return Err("a nudge needs a title or a body".into());
        }
        let kind = kind
            .filter(|k| KINDS.contains(&k.as_str()))
            .unwrap_or_else(|| "nudge".into());
        let mut seen = Vec::new();
        let actions = actions
            .unwrap_or_default()
            .into_iter()
            .filter_map(|a| {
                let label = clip(&a.label, MAX_LABEL);
                (valid_action_id(&a.id) && !label.is_empty() && !seen.contains(&a.id)).then(|| {
                    seen.push(a.id.clone());
                    NudgeAction { id: a.id, label }
                })
            })
            .take(MAX_ACTIONS)
            .collect();
        let mascot = mascot
            .filter(|m| MASCOT_STATES.contains(&m.as_str()))
            .unwrap_or_else(|| "happy".into());
        Ok(Nudge {
            id,
            kind,
            title,
            body,
            actions,
            mascot,
        })
    }

    /// Identity for de-duplication (`"7"` and `7` are the same nudge).
    pub fn key(&self) -> String {
        match &self.id {
            Value::String(s) => s.clone(),
            other => other.to_string(),
        }
    }

    fn same_content(&self, other: &Nudge) -> bool {
        self.kind == other.kind && self.title == other.title && self.body == other.body
    }
}

// ------------------------------------------------------------------ toast privacy

/// What a Windows toast says for a nudge of `kind`: `("Mentor", generic line)`. Toasts can show on
/// the lock screen and in the Action Center, which anyone at the computer can read, so they never
/// carry the real title or body (CONTRACTS.md section 9, N's privacy rule; same wording style as
/// N's Web Push payload). Only the in-app balloon shows the real text.
pub fn toast_text(kind: &str) -> (&'static str, &'static str) {
    let body = match kind {
        "checkin" => "Mentor có một câu hỏi nhanh cho bạn.",
        "deadline" => "Bạn có một hạn sắp tới.",
        "review" => "Đến giờ ôn nhanh.",
        "focus_end" => "Hết giờ tập trung.",
        "celebration" => "Mentor có tin vui cho bạn.",
        "report" => "Tổng kết của bạn đã sẵn sàng.",
        _ => "Mentor có lời nhắn cho bạn.",
    };
    ("Mentor", body)
}

/// Toast buttons, as N's Web Push does: `answer:<x>` left out (an answer is content and needs the
/// app), the others with fixed labels (a label could repeat private text).
pub fn toast_actions(actions: &[NudgeAction]) -> Vec<NudgeAction> {
    actions
        .iter()
        .filter_map(|a| {
            let label = match a.id.as_str() {
                "open" => "Mở",
                "snooze_1h" => "Nhắc lại sau 1 giờ",
                "done" => "Xong",
                "start_focus" => "Bắt đầu tập trung",
                _ => return None,
            };
            Some(NudgeAction { id: a.id.clone(), label: label.into() })
        })
        .collect()
}

// ------------------------------------------------------------------ queue

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Pushed {
    /// Nothing was on screen: this one is current now.
    ShowNow,
    /// Waits behind the current one.
    Queued,
    /// The current nudge got new text or actions (same id): render it again.
    Updated,
    /// Already shown, on screen or waiting (same id, or the same text as one waiting or on screen).
    Duplicate,
}

/// One nudge on screen at a time, the rest in arrival order.
#[derive(Default, Debug)]
pub struct NudgeQueue {
    current: Option<Nudge>,
    pending: VecDeque<Nudge>,
    recent: VecDeque<String>,
}

impl NudgeQueue {
    pub fn current(&self) -> Option<&Nudge> {
        self.current.as_ref()
    }

    #[cfg(test)]
    pub fn pending_len(&self) -> usize {
        self.pending.len()
    }

    /// Already shown and finished (balloon or toast).
    pub fn was_shown(&self, key: &str) -> bool {
        self.recent.iter().any(|k| k == key)
    }

    /// Remembers a nudge shown somewhere else (a toast), so a replay is not shown again.
    pub fn remember(&mut self, key: String) {
        if self.was_shown(&key) {
            return;
        }
        self.recent.push_back(key);
        while self.recent.len() > RECENT {
            self.recent.pop_front();
        }
    }

    pub fn push(&mut self, n: Nudge) -> Pushed {
        let key = n.key();
        if self.was_shown(&key) {
            return Pushed::Duplicate;
        }
        if let Some(cur) = self.current.as_mut() {
            if cur.key() == key {
                if *cur == n {
                    return Pushed::Duplicate;
                }
                *cur = n;
                return Pushed::Updated;
            }
            if cur.same_content(&n) {
                // The same reminder again under a new id: the newer record gets the clicks.
                cur.id = n.id;
                cur.actions = n.actions;
                return Pushed::Duplicate;
            }
        }
        if let Some(p) = self
            .pending
            .iter_mut()
            .find(|p| p.key() == key || p.same_content(&n))
        {
            *p = n;
            return Pushed::Duplicate;
        }
        if self.current.is_none() {
            self.current = Some(n);
            return Pushed::ShowNow;
        }
        self.pending.push_back(n);
        while self.pending.len() > MAX_PENDING {
            if let Some(old) = self.pending.pop_front() {
                self.remember(old.key());
            }
        }
        Pushed::Queued
    }

    /// The nudge `key` left the screen (action, close, timeout). Returns the next one, now current.
    /// A stale key (not the current nudge) changes nothing and returns `None`.
    pub fn finish(&mut self, key: &str) -> Option<&Nudge> {
        if self.current.as_ref().map(Nudge::key).as_deref() != Some(key) {
            return None;
        }
        self.remember(key.to_owned());
        self.current = self.pending.pop_front();
        self.current.as_ref()
    }

    /// Drops everything (the chat panel opened, the bubble was hidden, nudges were turned off).
    /// The dropped ones count as shown: the chat has them.
    pub fn clear(&mut self) {
        let keys: Vec<String> = self
            .current
            .take()
            .into_iter()
            .chain(self.pending.drain(..))
            .map(|n| n.key())
            .collect();
        for k in keys {
            self.remember(k);
        }
    }
}

// ------------------------------------------------------------------ routing

/// How nudges reach the user (`nudge_mode` in `bubble.json`, tray "Nhắc nhở: ...").
#[derive(Clone, Copy, PartialEq, Eq, Debug, Default, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NudgeMode {
    /// Speech balloon beside the bubble; a Windows toast when the balloon cannot be seen.
    #[default]
    Balloon,
    /// Always a Windows toast.
    Toast,
    /// Nothing outside the chat panel (the badge still counts).
    Off,
}

impl<'de> Deserialize<'de> for NudgeMode {
    /// Lenient like `BubbleMode`: missing, null or unknown means the default.
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        Ok(match Option::<String>::deserialize(d)?.as_deref() {
            Some("toast") => NudgeMode::Toast,
            Some("off") => NudgeMode::Off,
            _ => NudgeMode::Balloon,
        })
    }
}

/// What Windows says about the user (`SHQueryUserNotificationState`). Other platforms do not detect
/// it yet and always report `Present` (`win_shell::presence` in main.rs); routing and its tests
/// still cover every state.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
#[cfg_attr(not(windows), allow(dead_code))]
pub enum Presence {
    Present,
    /// Full-screen app, game or presentation: no balloon over it.
    Busy,
    /// Locked, screen saver, or another user's session.
    Away,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Route {
    Balloon,
    Toast,
    /// The chat panel is open: the page shows the nudge itself.
    Panel,
    Off,
}

pub struct RouteInput {
    pub mode: NudgeMode,
    pub signed_in: bool,
    pub panel_visible: bool,
    pub bubble_visible: bool,
    pub presence: Presence,
    /// Narrator, NVDA, JAWS...: a toast is announced, a balloon in a background window is not.
    pub screen_reader: bool,
}

pub fn route(i: &RouteInput) -> Route {
    if !i.signed_in || i.mode == NudgeMode::Off {
        return Route::Off;
    }
    if i.panel_visible && i.presence == Presence::Present {
        return Route::Panel;
    }
    if i.mode == NudgeMode::Toast
        || !i.bubble_visible
        || i.presence != Presence::Present
        || i.screen_reader
    {
        return Route::Toast;
    }
    Route::Balloon
}

// ------------------------------------------------------------------ balloon placement

/// Which side of the balloon the bubble is on; the tail and the transform origin point there.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Side {
    Left,
    Right,
}

#[derive(Clone, Copy, Debug)]
pub struct BalloonPlace {
    /// Physical window rectangle.
    pub rect: Rect,
    pub side: Side,
    /// Logical px from the window's top to the bubble's center (where the tail points).
    pub anchor_y: f64,
}

/// Balloon window beside the bubble window `bubble_win`, on the side away from the nearest
/// screen edge, inside the work area `wa` (physical, DPI `scale`). `content_h` is the logical
/// height the page asked for.
pub fn balloon_place(wa: Rect, scale: f64, bubble_win: Rect, content_h: f64) -> BalloonPlace {
    let (pad_x, pad_y, size) = circle(scale, bubble_win.w, bubble_win.h);
    let (bx, by) = (bubble_win.x + pad_x, bubble_win.y + pad_y);
    let (cx, cy) = (bx + size / 2, by + size / 2);
    let w = px(BALLOON_W, scale).min(wa.w);
    let h = px(content_h.clamp(BALLOON_MIN_H, BALLOON_MAX_H), scale).min(wa.h);
    let gap = px(BALLOON_GAP, scale);
    let m = px(EDGE_MARGIN, scale);

    let bubble_on_right = cx > wa.x + wa.w / 2;
    let (side, x) = if bubble_on_right {
        (Side::Right, bx - gap - w)
    } else {
        (Side::Left, bx + size + gap)
    };
    // Grow away from the nearer horizontal edge: up from a bubble in the lower half.
    let from_end = px(TAIL_FROM_END, scale);
    let y = if cy > wa.y + wa.h / 2 {
        cy + from_end - h
    } else {
        cy - from_end
    };
    // Horizontal: never pushed back over the bubble; only a work area narrower than bubble plus
    // balloon (not a real screen) would need that.
    let x = if bubble_on_right {
        x.max(wa.x)
    } else {
        x.min(wa.right() - w)
    };
    let y = fit(y, h, wa.y, wa.h, m);
    let rect = Rect { x, y, w, h };
    let h_l = h as f64 / scale;
    let anchor = ((cy - y) as f64 / scale).clamp(TAIL_MIN.min(h_l / 2.0), (h_l - TAIL_MIN).max(h_l / 2.0));
    BalloonPlace {
        rect,
        side,
        anchor_y: anchor,
    }
}

// ------------------------------------------------------------------ mascot

/// The bubble's mascot state. `panel` is what the chat page reported (`desktop_mascot`), `balloon`
/// the hint of the nudge on screen, if any. A `calm` page (serious topic, crisis) wins over every
/// playful state; the one-shot greeting wave is played by the bubble page itself.
pub fn bubble_mascot<'a>(signed_in: bool, panel: &'a str, balloon: Option<&'a str>) -> &'a str {
    if !signed_in {
        return "idle";
    }
    if panel == "calm" {
        return "calm";
    }
    if let Some(hint) = balloon {
        return hint;
    }
    panel
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn nudge(id: &str, title: &str) -> Nudge {
        Nudge::new(
            json!(id),
            Some("checkin".into()),
            Some(title.into()),
            Some("body".into()),
            None,
            None,
        )
        .unwrap()
    }

    #[test]
    fn validation_clips_and_filters() {
        let acts = vec![
            NudgeAction { id: "open".into(), label: "Mở chat".into() },
            NudgeAction { id: "Bad Id".into(), label: "x".into() },
            NudgeAction { id: "open".into(), label: "again".into() },
            NudgeAction { id: "snooze_1h".into(), label: "  Để sau  ".into() },
            NudgeAction { id: "answer:Có".into(), label: "Có".into() },
            NudgeAction { id: "done".into(), label: "Xong".into() },
        ];
        let n = Nudge::new(
            json!(42),
            Some("weird".into()),
            Some("  Chào   buổi sáng ".into()),
            Some("a\n\n  b   c".into()),
            Some(acts),
            Some("dance".into()),
        )
        .unwrap();
        assert_eq!(n.kind, "nudge");
        assert_eq!(n.title, "Chào buổi sáng");
        assert_eq!(n.body, "a\n\nb c");
        assert_eq!(n.mascot, "happy");
        let ids: Vec<_> = n.actions.iter().map(|a| a.id.as_str()).collect();
        assert_eq!(ids, ["open", "snooze_1h", "answer:Có"]);
        assert_eq!(n.actions[1].label, "Để sau");
        assert_eq!(n.key(), "42");

        let long = "ư".repeat(500);
        let n = Nudge::new(json!("x"), None, Some(long.clone()), Some(long), None, Some("calm".into()))
            .unwrap();
        assert_eq!(n.title.chars().count(), MAX_TITLE);
        assert!(n.title.ends_with('…'));
        assert_eq!(n.body.chars().count(), MAX_BODY);
        assert_eq!(n.mascot, "calm");

        for bad in [json!(""), json!("  "), json!(null), json!(1.5), json!({"a": 1}), json!("a\u{0}b")] {
            assert!(Nudge::new(bad.clone(), None, Some("t".into()), None, None, None).is_err(), "{bad}");
        }
        assert!(Nudge::new(json!("x"), None, Some(" ".into()), Some("\n".into()), None, None).is_err());
        assert!(valid_action_id("answer:7 giờ"));
        assert!(!valid_action_id("answer:"));
        assert!(!valid_action_id(":x"));
        assert!(!valid_action_id("open\n"));
        assert!(!valid_action_id("answer:a\u{7}"));
    }

    #[test]
    fn toasts_never_carry_the_real_text_or_answers() {
        let n = Nudge::new(
            json!("n1"),
            Some("checkin".into()),
            Some("Hôm nay bạn thấy thế nào?".into()),
            Some("Hôm qua bạn nói hơi mệt vì chuyện ở lớp.".into()),
            Some(vec![
                NudgeAction { id: "answer:Ổn".into(), label: "Ổn".into() },
                NudgeAction { id: "open".into(), label: "Trò chuyện".into() },
                NudgeAction { id: "snooze_1h".into(), label: "Để sau".into() },
            ]),
            None,
        )
        .unwrap();
        let (title, body) = toast_text(&n.kind);
        assert_eq!(title, "Mentor");
        assert!(!body.contains("thế nào") && !body.contains("mệt"));
        let buttons = toast_actions(&n.actions);
        let ids: Vec<_> = buttons.iter().map(|a| a.id.as_str()).collect();
        assert_eq!(ids, ["open", "snooze_1h"]);
        // fixed labels, not the sender's
        assert_eq!(buttons[0].label, "Mở");
        assert_eq!(buttons[1].label, "Nhắc lại sau 1 giờ");
        // every kind has its own generic line; unknown ones get the generic nudge line
        let mut bodies: Vec<_> = KINDS.iter().map(|k| toast_text(k).1).collect();
        bodies.dedup();
        assert_eq!(bodies.len(), KINDS.len());
        assert_eq!(toast_text("whatever"), toast_text("nudge"));
    }

    #[test]
    fn queue_shows_one_at_a_time_in_order() {
        let mut q = NudgeQueue::default();
        assert_eq!(q.push(nudge("a", "A")), Pushed::ShowNow);
        assert_eq!(q.push(nudge("b", "B")), Pushed::Queued);
        assert_eq!(q.push(nudge("c", "C")), Pushed::Queued);
        assert_eq!(q.current().unwrap().key(), "a");
        // a stale finish (an old balloon's timer) changes nothing
        assert!(q.finish("b").is_none());
        assert_eq!(q.current().unwrap().key(), "a");
        assert_eq!(q.finish("a").unwrap().key(), "b");
        assert_eq!(q.finish("b").unwrap().key(), "c");
        assert!(q.finish("c").is_none());
        assert!(q.current().is_none());
        // the next push shows right away
        assert_eq!(q.push(nudge("d", "D")), Pushed::ShowNow);
    }

    #[test]
    fn queue_collapses_duplicates() {
        let mut q = NudgeQueue::default();
        assert_eq!(q.push(nudge("a", "A")), Pushed::ShowNow);
        // same id, same content: nothing to do
        assert_eq!(q.push(nudge("a", "A")), Pushed::Duplicate);
        // same id, new text: re-render
        assert_eq!(q.push(nudge("a", "A2")), Pushed::Updated);
        assert_eq!(q.current().unwrap().title, "A2");
        // same text under a new id: collapses into the one on screen, clicks go to the newer id
        assert_eq!(q.push(nudge("a-again", "A2")), Pushed::Duplicate);
        assert_eq!(q.current().unwrap().key(), "a-again");
        assert_eq!(q.pending_len(), 0);
        // waiting ones collapse too (by id or by text), keeping their place
        assert_eq!(q.push(nudge("b", "B")), Pushed::Queued);
        assert_eq!(q.push(nudge("c", "C")), Pushed::Queued);
        assert_eq!(q.push(nudge("b", "B2")), Pushed::Duplicate);
        assert_eq!(q.push(nudge("c2", "C")), Pushed::Duplicate);
        assert_eq!(q.pending_len(), 2);
        assert_eq!(q.finish("a-again").unwrap().title, "B2");
        assert_eq!(q.finish("b").unwrap().key(), "c2");
        // already shown: a replay after a reconnect is ignored
        q.finish("c2");
        assert_eq!(q.push(nudge("b", "B2")), Pushed::Duplicate);
        assert_eq!(q.push(nudge("a-again", "A2")), Pushed::Duplicate);
        // numbers and strings are the same id
        let n7 = Nudge::new(json!(7), None, Some("x".into()), None, None, None).unwrap();
        let s7 = Nudge::new(json!("7"), None, Some("y".into()), None, None, None).unwrap();
        assert_eq!(q.push(n7), Pushed::ShowNow);
        assert_eq!(q.push(s7), Pushed::Updated);
    }

    #[test]
    fn queue_caps_waiting_and_clear_remembers() {
        let mut q = NudgeQueue::default();
        q.push(nudge("cur", "cur"));
        for i in 0..(MAX_PENDING + 3) {
            assert_eq!(q.push(nudge(&format!("p{i}"), &format!("P{i}"))), Pushed::Queued);
        }
        assert_eq!(q.pending_len(), MAX_PENDING);
        // the oldest waiting ones were dropped (and count as shown)
        assert!(q.was_shown("p0") && q.was_shown("p2") && !q.was_shown("p3"));
        assert_eq!(q.finish("cur").unwrap().key(), "p3");
        q.clear();
        assert!(q.current().is_none());
        assert_eq!(q.pending_len(), 0);
        assert!(q.was_shown("p3") && q.was_shown("p6"));
        assert_eq!(q.push(nudge("p6", "P6")), Pushed::Duplicate);
        // the memory is bounded
        for i in 0..100 {
            q.remember(format!("r{i}"));
        }
        assert!(!q.was_shown("p6") && q.was_shown("r99"));
    }

    #[test]
    fn routing_rules() {
        let base = RouteInput {
            mode: NudgeMode::Balloon,
            signed_in: true,
            panel_visible: false,
            bubble_visible: true,
            presence: Presence::Present,
            screen_reader: false,
        };
        assert_eq!(route(&base), Route::Balloon);
        assert_eq!(route(&RouteInput { panel_visible: true, ..base }), Route::Panel);
        assert_eq!(route(&RouteInput { bubble_visible: false, ..base }), Route::Toast);
        assert_eq!(route(&RouteInput { presence: Presence::Away, ..base }), Route::Toast);
        assert_eq!(route(&RouteInput { presence: Presence::Busy, ..base }), Route::Toast);
        assert_eq!(route(&RouteInput { screen_reader: true, ..base }), Route::Toast);
        assert_eq!(route(&RouteInput { mode: NudgeMode::Toast, ..base }), Route::Toast);
        // a locked session with the panel left open still gets the toast (Action Center)
        assert_eq!(
            route(&RouteInput { panel_visible: true, presence: Presence::Away, ..base }),
            Route::Toast
        );
        assert_eq!(route(&RouteInput { mode: NudgeMode::Off, ..base }), Route::Off);
        assert_eq!(route(&RouteInput { signed_in: false, ..base }), Route::Off);
    }

    #[test]
    fn nudge_mode_is_lenient() {
        let p = |s: &str| serde_json::from_str::<NudgeMode>(s).unwrap();
        assert_eq!(p(r#""toast""#), NudgeMode::Toast);
        assert_eq!(p(r#""off""#), NudgeMode::Off);
        assert_eq!(p(r#""balloon""#), NudgeMode::Balloon);
        assert_eq!(p(r#""loud""#), NudgeMode::Balloon);
        assert_eq!(p("null"), NudgeMode::Balloon);
        assert_eq!(serde_json::to_string(&NudgeMode::Toast).unwrap(), r#""toast""#);
    }

    #[test]
    fn mascot_priority() {
        assert_eq!(bubble_mascot(false, "thinking", Some("happy")), "idle");
        assert_eq!(bubble_mascot(true, "calm", Some("happy")), "calm");
        assert_eq!(bubble_mascot(true, "thinking", Some("happy")), "happy");
        assert_eq!(bubble_mascot(true, "sleepy", None), "sleepy");
        assert_eq!(bubble_mascot(true, "idle", None), "idle");
    }

    // ---------------------------------------------------------------- placement

    fn overlaps(a: Rect, b: Rect) -> bool {
        a.x < b.right() && b.x < a.right() && a.y < b.bottom() && b.y < a.bottom()
    }

    fn inside(r: Rect, wa: Rect) -> bool {
        r.x >= wa.x && r.y >= wa.y && r.right() <= wa.right() && r.bottom() <= wa.bottom()
    }

    fn check_spot(wa: Rect, scale: f64, b: Rect, content_h: f64) -> BalloonPlace {
        let p = balloon_place(wa, scale, b, content_h);
        let r = p.rect;
        let (pad, _, c) = circle(scale, b.w, b.h);
        let circ = Rect { x: b.x + pad, y: b.y + pad, w: c, h: c };
        assert!(inside(r, wa), "balloon {r:?} outside {wa:?} for bubble {b:?}");
        assert!(!overlaps(r, circ), "balloon {r:?} covers the bubble {circ:?}");
        // beside the bubble, away from the screen edge it is docked to
        let on_right = circ.x + c / 2 > wa.x + wa.w / 2;
        if on_right {
            assert_eq!(p.side, Side::Right);
            assert!(r.right() <= circ.x, "{r:?} {circ:?}");
        } else {
            assert_eq!(p.side, Side::Left);
            assert!(r.x >= circ.right(), "{r:?} {circ:?}");
        }
        // the tail points at the bubble whenever the bubble's center is level with the window
        let h_l = r.h as f64 / scale;
        assert!(p.anchor_y >= 0.0 && p.anchor_y <= h_l, "{p:?}");
        let cy = circ.y + c / 2;
        if cy >= r.y + px(TAIL_MIN, scale) && cy <= r.bottom() - px(TAIL_MIN, scale) {
            let tail_phys = r.y as f64 + p.anchor_y * scale;
            assert!((tail_phys - cy as f64).abs() <= 2.0, "tail {tail_phys} vs bubble {cy}");
        }
        p
    }

    fn walk_edges(wa: Rect, scale: f64, content_h: f64) {
        let win = crate::bubble_win_size(scale);
        for i in 0..=24 {
            let t = i as f64 / 24.0;
            let along_x = wa.x + ((wa.w - win) as f64 * t) as i32;
            let along_y = wa.y + ((wa.h - win) as f64 * t) as i32;
            for (x, y) in [
                (wa.x, along_y),
                (wa.right() - win, along_y),
                (along_x, wa.y),
                (along_x, wa.bottom() - win),
            ] {
                let (bx, by) = crate::snapped(wa, scale, x, y, win, win);
                check_spot(wa, scale, Rect { x: bx, y: by, w: win, h: win }, content_h);
            }
        }
    }

    #[test]
    fn balloon_stays_beside_the_bubble_on_every_edge_spot() {
        let screens = [
            (Rect { x: 0, y: 0, w: 1920, h: 1032 }, 1.0),
            (Rect { x: -2880, y: -400, w: 2880, h: 1548 }, 1.5),
            (Rect { x: 1920, y: 260, w: 1200, h: 1860 }, 1.25),
            // 1366x768 at 125% with a 48px (60 physical) taskbar
            (Rect { x: 0, y: 0, w: 1366, h: 708 }, 1.25),
            // 1366x768 at 100%, taskbar on the left
            (Rect { x: 62, y: 0, w: 1304, h: 768 }, 1.0),
        ];
        for (wa, scale) in screens {
            for h in [BALLOON_MIN_H, 150.0, 240.0, BALLOON_MAX_H, 2000.0] {
                walk_edges(wa, scale, h);
            }
        }
    }

    #[test]
    fn balloon_default_corner_at_1366x768_125() {
        // the default spot: bottom-right, just above the taskbar
        let wa = Rect { x: 0, y: 0, w: 1366, h: 708 };
        let win = crate::bubble_win_size(1.25);
        let (pad, _, c) = circle(1.25, win, win);
        let b = Rect {
            x: wa.right() - px(EDGE_MARGIN, 1.25) - c - pad,
            y: wa.bottom() - px(24.0, 1.25) - c - pad,
            w: win,
            h: win,
        };
        let p = check_spot(wa, 1.25, b, 180.0);
        assert_eq!(p.side, Side::Right);
        assert_eq!((p.rect.w, p.rect.h), (px(BALLOON_W, 1.25), px(180.0, 1.25)));
        // opens upward from the bubble: the tail sits low on the card
        assert!(p.anchor_y > 180.0 / 2.0, "{p:?}");
        // top-left corner: opens to the right and downward
        let b = Rect { x: wa.x + 4, y: wa.y + 4, w: win, h: win };
        let p = check_spot(wa, 1.25, b, 180.0);
        assert_eq!(p.side, Side::Left);
        assert!(p.anchor_y < 180.0 / 2.0, "{p:?}");
    }

    #[test]
    fn balloon_tolerates_a_bubble_window_wider_than_asked() {
        // Windows may enforce a minimum width on the bubble window (see `circle`)
        let wa = Rect { x: 0, y: 0, w: 1920, h: 1032 };
        check_spot(wa, 1.0, Rect { x: 1920 - 12 - 56 - 37, y: 500, w: 130, h: 72 }, 160.0);
        check_spot(wa, 1.0, Rect { x: 12 - 37, y: 500, w: 130, h: 72 }, 160.0);
    }
}

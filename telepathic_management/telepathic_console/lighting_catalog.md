# Grace's lighting catalogue

Colours and effects are editable data. Examples are suggestions, with no fixed occasions or triggers.
The single JSON block is read whenever a lighting request arrives. Brightness is 0–1.
`rhythm_pattern` contains successive brightness multipliers, equally spaced over `rhythm_seconds`.

```json
{
  "colors": {
    "mint": "#58C77E", "rose": "#B84669", "red": "#FF0000",
    "white": "#FFFFFF", "green": "#00FF00", "gold": "#FFD700",
    "pumpkin": "#FF7518", "purple": "#800080", "sakura": "#FFB7C5"
  },
  "effects": {
    "rainbow": {"rainbow": true, "transition_speed": "slow", "brightness": 0.4, "duration_seconds": 120},
    "red_white_green": {"start_color": "red", "transition_colors": ["white"], "end_color": "green", "transition_speed": "slow"},
    "pumpkin_purple": {"start_color": "pumpkin", "end_color": "purple", "transition_speed": "slow"},
    "red_gold": {"start_color": "red", "end_color": "gold"},
    "sakura_glow": {"start_color": "sakura", "rhythm": "stationary", "brightness": 0.3},
    "dim": {"start_color": "gold", "rhythm": "stationary", "brightness": 0.05},
    "attention": {"start_color": "white", "rhythm": "blink_slow", "brightness": 0.6, "duration_seconds": 12},
    "siren": {"start_color": "red", "end_color": "white", "transition_seconds": 2, "intermediate_steps": 0, "duration_seconds": 12},
    "double_pulse": {"start_color": "rose", "rhythm": "pattern", "rhythm_seconds": 4, "rhythm_pattern": [0, 1, 0.2, 0.7, 0.1, 0, 0, 0]},
    "morse_hello": {"start_color": "mint", "rhythm": "morse", "morse_text": "HELLO", "duration_seconds": 30}
  }
}
```

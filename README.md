# Joint Object Control

Does working with a partner beat working alone — and does it matter whether the partner is a person, a recording, or an algorithm?

A cooperative target-acquisition experiment built in pygame, with an R analysis replicating and extending Wahn et al. (2016). Social and Cultural Dynamics exam project, BSc Cognitive Science, Aarhus University.

## The idea

A cursor has to be steered into a target and held there. The trick is that **control is split across axes**: one controller moves it horizontally, the other vertically. Neither can reach the target alone, so the pair has to coordinate.

That setup runs in four conditions:

| Condition | Horizontal | Vertical |
|---|---|---|
| **Individual** | you | you |
| **Cooperative** | you | a second person |
| **Playback** | you | a recording of an earlier partner |
| **AI** | you | an algorithm |

Playback is the control that makes the design work. It reproduces a real partner's movements exactly, but cannot respond to what you do. Comparing AI against playback therefore isolates **adaptiveness** — what a partner's ability to react to you is worth, holding the movements themselves constant.

## The experiment

`final_experiment.py`, pygame, 60 FPS.

Targets sit 12.8 cm from centre at five angles (0°, 22.5°, 45°, 67.5°, 90°), four repetitions each, shuffled — 20 trials plus 5 practice. The angle sets how the work is divided: at 0° and 90° a single axis does everything, 45° splits it evenly, and 22.5° and 67.5° give a roughly 70/30 split. Sweeping the angle sweeps the contribution ratio.

A trial is scored in two phases. **Approach** runs until the cursor enters the homing-in zone; **homing-in** runs from there until the cursor holds the target for a full second of dwell time. Both reaction time and path distance are logged per phase, so speed and efficiency can come apart.

Every frame of input is recorded to `recordings/` as JSON, which is what later feeds the playback condition. In the AI condition, control of the vertical and horizontal axis alternates across four blocks of five trials so the assignment isn't confounded with practice.

Error trials were defined following Wahn et al. — cursor leaves the homing-in zone after entering, or exits the screen — with an added criterion for failing to hold the dwell time. Under that definition no trials in this sample were errors.

## The analysis

`Soccult.Rmd` — cleaning through to figures, rendered in `Soccult.pdf`.

**Collective benefit** is the dyad's performance relative to the *better* of its two members. Above 1 means the pair beat its strongest individual; below 1 means it didn't. Computed separately for each phase and each contribution angle.

**Skill ratio** captures how similar two members are individually. Wahn et al. predicted that collective benefit rises as members become more evenly matched, with the relationship weakening at 70/30 splits where the stronger member's dominance compensates for the gap.

**Adaptiveness benefit** is the within-participant ratio of playback to AI at matched angles and phases — how much the AI's responsiveness buys over an identical but unresponsive partner.

Methods: paired *t*-tests and Wilcoxon signed-rank tests, repeated-measures ANOVA (`ezANOVA`) with partial eta squared and pairwise post-hoc comparisons, Pearson correlations for the skill-ratio analyses, and linear mixed models (`lmer`) for learning, with trial order predicting per-trial collective benefit and random intercepts and slopes per dyad.

## What was found

With **six dyads**, this is a small sample and the analysis treats most results as descriptive. Nothing below reached conventional significance.

The general direction is a **coordination cost rather than a collective benefit**. In the approach phase dyads travelled slightly further than individuals at both 0° and 90°. The clearest effect appears during homing-in at 90°, where the split is most asymmetric: cooperative path distance ran 238 units above individual (*d* = 0.48, *W* = 18, *p* = .156), and cooperative reaction time was slower than individual (5.24 s versus 2.78 s, *d* = 0.53). Fine positioning under maximal asymmetry is where coordination hurts most.

One reversal is worth noting: at 0° during homing-in, dyads were more efficient than individuals (300 versus 377 units), though the effect is small and non-significant.

The learning models ask whether dyads improve with practice — whether collective benefit grows across cooperative trials.

## Repository contents

| File | Contents |
|---|---|
| `final_experiment.py` | The pygame experiment: all four conditions, target generation, phase timing, frame-level logging |
| `Soccult.Rmd` | Full analysis pipeline with interpretation between steps |
| `Soccult.pdf` | Rendered output |
| `experiment_data.csv` | Frame-level trial data |
| `experiment_summary.csv` | Per-trial summary |
| `recordings/` | Per-participant JSON movement traces, used as playback partners |

## Running it

```bash
pip install pygame
python final_experiment.py
```

Individual and playback conditions use the arrow keys. In the cooperative condition player one takes the arrow keys for horizontal and player two takes `W`/`S` for vertical, so both participants share one keyboard.

Analysis needs R with `tidyverse` and `ez`.

## Known issues and limitations

- **Six dyads.** Power per angle × phase cell is very low, and the skill-ratio correlations in particular should be read as exploratory. This is stated in the analysis but bears repeating.
- **An asymmetry in the baselines.** Cooperative collective benefit uses the better of the two members as the individual baseline, while AI and playback average across both. 
- **The cooperative condition is excluded from the adaptiveness analysis**, because its data is dyad-level rather than per-participant and can't be matched to the within-person ratio.
- **`.RData` and `.Rhistory` are committed.** These are local session state and shouldn't be in version control; a `.gitignore` would clear this up.
- **Hardcoded screen geometry.** `PX_PER_CM = 28` calibrates the 12.8 cm target distance to one specific display. Running on different hardware changes the physical task without changing the code.

## Reference

Wahn, B., Schmitz, L., König, P., & Knoblich, G. (2016). Benefiting from being alike: Interindividual skill differences predict collective benefit in joint object control. Proceedings of the Annual Meeting of the Cognitive Science Society, 38. https://escholarship.org/uc/item/4zv166g0 

# Product

## Register

product

## Users

Non-technical Windows users who need to preserve visible WeChat group chat records for review or legal evidence preparation. They are usually operating under time pressure, with WeChat already open, and need a guided desktop tool instead of memorizing PowerShell commands.

## Product Purpose

This product captures authorized, visible WeChat desktop chat windows as ordered screenshot evidence, then writes manifests, metadata, logs, and SHA256 verification files. Success means the user can calibrate scrolling on their own computer, run a full capture, stop it reliably with a global hotkey, and verify the output without touching the command line.

## Brand Personality

Calm, precise, trustworthy. The interface should feel like an evidence-handling utility: clear steps, direct labels, strong status feedback, and no decorative flourish.

## Anti-references

Avoid marketing-page styling, generic AI gradients, decorative glass panels, playful chat app visuals, and dense developer-console UI. Do not make critical controls depend on the app staying in front during capture because WeChat will often regain focus.

## Design Principles

- Put the current task and next action in view at all times.
- Treat stopping as a safety-critical action: global hotkey first, app button second.
- Preserve evidence context: every run should make output location, run status, and verification state obvious.
- Hide advanced tuning until the basic calibration workflow is understood.
- Keep the CLI behavior compatible so existing PowerShell workflows remain valid.

## Accessibility & Inclusion

Use high-contrast text, standard Windows controls, visible focus states, and clear Chinese labels. Do not rely on color alone for success or error states. Motion should be minimal and state-driven only.

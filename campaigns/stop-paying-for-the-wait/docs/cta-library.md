# CTA library

The campaign's primary action is always “Build my savings plan.” Secondary CTAs may clarify the next step but must not imply that Seasons performs an external cancellation.

## Funnel mapping

| Stage | User question | Approved CTA | Recommended destination |
|---|---|---|---|
| Awareness | Why does timing matter? | See the billing math | Worked-example section |
| Awareness | Is this real? | Check the assumptions | Methodology and sources |
| Consideration | Could this apply to my shows? | Build my savings plan | Seasons activation path |
| Consideration | How does Seasons decide? | See how the plan works | Product mechanism explainer |
| Conversion, iOS | What do I do now? | Build my savings plan | Verified App Store or app handoff |
| Conversion, Android | Can I use it yet? | Join Android updates | Android-specific waitlist only |
| Community | Does the logic hold? | Audit the math | Full Reddit post or methodology |
| Retention | What should I plan next? | Add another show | In-app title flow |

## Platform recommendations

### Instagram

- Carousel slide 1: “Swipe to see the billing math.”
- Carousel slide 5: “Build my savings plan.”
- Story frames 1 and 2: “Tap through for the math.”
- Story frame 3: “Build my savings plan.”
- Reel caption: “Build my savings plan.”

### TikTok

- First four seconds: no CTA, only the hook.
- Result frame: “Build my savings plan.”
- Post caption: “Build my savings plan at getseasons.app.”

### Reddit

Lead with the calculation, not the app. Choose one low-pressure CTA after the full assumptions:

- “What would make this calculation wrong for your setup?”
- “Audit the assumptions and tell me what I missed.”
- “If this is useful, the full method is at getseasons.app.”
- “I built Seasons to make this plan personal. Happy to explain how the calculation works.”

Do not use “Download now,” urgency language, repeated links, or the same CTA across unrelated communities.

## Attribution links

Use a distinct `utm_content` value for every asset. Until a dedicated campaign page is live and verified, use the site root:

```text
https://getseasons.app/?utm_source=instagram&utm_medium=organic_social&utm_campaign=stop_paying_for_the_wait&utm_content=carousel_apple_01
https://getseasons.app/?utm_source=instagram&utm_medium=organic_social&utm_campaign=stop_paying_for_the_wait&utm_content=story_apple_01
https://getseasons.app/?utm_source=instagram&utm_medium=organic_social&utm_campaign=stop_paying_for_the_wait&utm_content=reel_apple_01
https://getseasons.app/?utm_source=tiktok&utm_medium=organic_social&utm_campaign=stop_paying_for_the_wait&utm_content=proof_video_apple_01
https://getseasons.app/?utm_source=reddit&utm_medium=community&utm_campaign=stop_paying_for_the_wait&utm_content={community}_{variant}
```

Replace `{community}` and `{variant}` with lowercase values before posting. Never attach campaign parameters to source links. Keep evidence links clean.


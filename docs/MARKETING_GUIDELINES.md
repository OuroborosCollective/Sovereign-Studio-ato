# NOCode Studio - Marketing & Distribution Guidelines

## Core Principles

When communicating about NOCode Studio in any user-facing or public context (including automated marketing, social media, Play Store descriptions, and beta testing outreach), it must **only** be referred to by its consumer-facing name: **NOCode Studio**.

### Do's:
- **Product Name:** Always refer to the product as "NOCode Studio".
- **Value Proposition:** Highlight its capabilities as a premium, no-code app builder.
- **Beta Offers:** Emphasize the savings and exclusivity ("Save €6.49, get a premium no-code app builder for free, limited to 135 beta testers!").
- **Target Audience:** Address regular users, creators, and entrepreneurs looking to build apps easily.

### Don'ts:
- **No Internal Terminology:** Never mention "NOCode Studio", "Ghost Pilot", "Agents", "Autonomous Repository Architect", or any internal system components.
- **No Technical Complexity:** Never refer to the underlying repository, GitHub Actions, CI/CD pipelines, or how the APK/AAB is generated.
- **No Developmental Focus:** Do not position it as a developer tool or IDE; it is a user-friendly product.

## Beta Distribution Strategy
We have 135 Play Store promo codes available for our final Google Play Store release test. The goal is to distribute these to users who will actively use the app for 14 days, providing valuable testing data while receiving a €6.49 product entirely for free.

### The Pitch
> "Want to build your own apps without writing a single line of code? We're looking for 135 beta testers for our upcoming release of NOCode Studio. Normally €6.49, you can get it for FREE right now! Just use the app for two weeks and share your feedback. Claim your code before they're gone!"

## Enforcing these Guidelines in Automation
All automated marketing scripts (e.g., in `launch-bot-v1/marketing/`) must adhere strictly to these rules. System prompts provided to LLMs generating marketing content must explicitly forbid mentioning repositories, CI/CD pipelines, or the "Sovereign" name.
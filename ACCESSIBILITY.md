# Accessibility

We want everyone, including people with disabilities and people who use assistive technology, to be able to read this profile and to contribute to it.

This repository contains only documentation: the profile [`README.md`](./README.md) shown on [github.com/roma-bb8](https://github.com/roma-bb8). This document explains what we aim for, what we know is not perfect yet, and how to tell us about a barrier.

## Priorities

- **Accessibility target:** we work toward [WCAG 2.2 Level AA](https://www.w3.org/TR/WCAG22) where it applies to written content. This is a goal, not a claim of verified conformance. No formal evaluation has been done.
- **Screen readers:** content uses plain Markdown, so headings, lists, and links are real structure that VoiceOver, NVDA, JAWS, and similar tools can navigate.
- **Readable content:** plain language, descriptive link text, and meaningful alternative text for images.
- **Languages:** the README is in English. If a translation is added, it will be marked with its language.

GitHub renders the page itself, so keyboard support, focus indicators, and color contrast of the page come from GitHub and your own theme settings.

## Known limitations

- The animated banner at the top of the README is an image of flickering digits. Its meaning is given in its alt text and in its `<title>` and `<desc>`. The animation stops when your system asks for reduced motion.
- The table of technologies is wide, and some rows hold many links. On a narrow screen it scrolls sideways.
- The text is only in English, and English is not the author's first language, so wording may be unclear.

Fixes for these are welcome as pull requests, see [Contributing](./CONTRIBUTING.md).

## Contributor expectations

If you change the README or any document here:

- Use a logical heading hierarchy and do not skip levels.
- Use real Markdown lists and headings, not text formatted to look like them.
- Use unique, descriptive link text. Avoid "click here" and "read more".
- Give every image meaningful alternative text, following the [W3C alt decision tree](https://www.w3.org/WAI/tutorials/images/decision-tree/). Use empty alt text only for purely decorative images.
- Do not use color or emoji as the only way to convey meaning.
- Prefer a short text description over an image of text.
- Preview the change on GitHub and check that it reads sensibly with the keyboard and, if you can, a screen reader.

## Reporting accessibility issues

If you run into a barrier, please tell us. We treat accessibility reports as expertise, not complaints.

1. [Open an accessibility issue](../../issues/new?template=accessibility.yml).
2. If you can, include:
   - What you were trying to do and what went wrong.
   - Your operating system, browser, and assistive technology.
   - A screenshot or recording, only if you are comfortable sharing one.

You do not need to share a diagnosis or any personal information. If you prefer not to use GitHub issues, use the contact options on the [@roma-bb8](https://github.com/roma-bb8) profile.

### How we respond

- We will acknowledge the report respectfully.
- We will explain next steps and any limits, for example when the barrier comes from GitHub itself and not from this content.
- Where possible, we will suggest a workaround while a fix is in progress.
- We will let you know when a fix is made so you can check it.

This is a personal, volunteer project, so we cannot promise fixed response times.

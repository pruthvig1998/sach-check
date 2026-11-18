# Motion libraries (served by Sach from its own domain)

These three files are third-party code. Sach's MIT licence does not cover them.

| File | Version | Source | Licence |
|---|---|---|---|
| `gsap-3.12.5.min.js` | GSAP 3.12.5 | `cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js` | GreenSock / Webflow "Standard License" (https://gsap.com/standard-license): free to use, including commercially, on websites. Not open source. The licence forbids removing its notices (kept in the file header) and some uses (no-code animation builders); Webflow may revoke it. |
| `ScrollTrigger-3.12.5.min.js` | GSAP ScrollTrigger 3.12.5 | `cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js` | As GSAP above. |
| `lenis-1.1.13.min.js` | Lenis 1.1.13 | `cdn.jsdelivr.net/npm/lenis@1.1.13/dist/lenis.min.js` | MIT, Copyright (c) 2024 darkroom.engineering. The notice is prepended to the file, as the MIT licence requires; the source-map comment was removed (the map is not shipped). |

Copied on 18 November 2026. `sach/motion.py` pins the SHA-256 of each file, and `tests/test_knowledge.py` checks them.

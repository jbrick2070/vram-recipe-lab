# MiniMax H3 License Authorization — GRANTED

**Status change:** the US-excluded-territory block on MiniMax H3 is LIFTED for
this operator by separate written authorization, per the path Section II of
the MiniMax H3 Community License provides.

## The grant

- **From:** API@minimax.io (the contact address named in the license)
- **Date:** 2026-08-08 00:54 UTC
- **To:** info@blueberrykaleyogabooks.com
- **Subject:** MiniMax H3 License Authorization
- **Gmail message id:** 19fdedd7f206db6a (archived in the operator's inbox)

Full text (verbatim):

> Dear Jeffrey Brick,
>
> Thank you for your request and for choosing MiniMax H3.
>
> This email is to confirm that MiniMax authorizes Blueberrky Kale Yoga Books
> to use MiniMax H3 and MiniMax H3 Works, subject to and conditioned upon
> Blueberrky Kale Yoga Books's continued compliance with the commitments and
> representations set forth in its request email.
>
> For any questions, please contact api@minimax.io.
>
> Sincerely,
> MiniMax H3 Team

(The grantee name typo "Blueberrky" is in the original.)

## Scope and conditions

The authorization is conditioned on **the commitments and representations in
Jeffrey's request submission** (2026-08-07). Operating assumptions consistent
with that request and this lab's rules: local, offline, non-commercial radio
drama production on the operator's own hardware; no hosted service, no
redistribution of the weights. The underlying Community License otherwise
continues to apply (Acceptable Use Policy, no training other models on
Outputs, attribution encouragements, etc.).

## Effect on the lab

- The six `h3_*` recipes' BLOCKED reason changes from "license: US excluded
  territory" to "weights downloading" and clears entirely once the manifest
  shows the files.
- Weight set being downloaded 2026-08-08 into `C:\ComfyUI-Models`:
  fl2va_pruned_int8_convrot (19.53 GiB), ref2va_pruned_int8_convrot
  (19.53 GiB), qwen3vl_32b nvfp4_awq (14.61 GiB), video VAE fp16 (4.85 GiB),
  audio VAE fp32 (0.56 GiB) — from `Comfy-Org/MiniMax-H3`.
- H3 runs remain gated on: the empty-output-bypass gate fix, the Sage-free
  boot lane (lab default), and human eyeball review of every H3 output.

# H3 music follow-up

Status: **TERMINAL - MACHINE-GATE FAILURE ON THE FINAL LEG**. Campaign
`h3music-followup-20260810T195909Z-ac3f65ee-attempt-001` completed 10 of 11
exploratory cold legs inside the 14.5 GiB absolute ceiling. The final f277
render saved a native-audio MP4, then its receipt recorded 14.722 GiB absolute
peak and the coordinator terminated the campaign under the hard gate. These
are machine-run outcomes, not music, mood, scene-fit, motion, or usability
judgments. Jobs 2–4 received the operator rulings recorded below; the later
prompt-only origin addendum retains its own **PENDING_HUMAN** questions.

The campaign produced 11 native-audio MP4 artifacts totaling 66.045 seconds by
the receipt-reported audio durations. No warm certification, production
promotion, dropdown entry, conditional bonus, or OTR change is claimed.

## Campaign and operator evidence

- Campaign lifecycle:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/lifecycle.jsonl`;
  45 rows, 5,441,991 bytes, SHA-256
  `b2471a7107a4693c5bda9bd933539b43cb43f5c2da8ab24c14d99bc11bc8b6e0`.
  The operator receipt verifies the whole hash chain. Sequence 45 is
  `campaign_failed`, status `FAILED`, event SHA-256
  `fb50427ae19eee6ebe6b6ff7b9c4252d99a9db7204b5430468d2c7b7721554f0`,
  at `2026-08-10T23:59:57Z`.
- Campaign launch receipt:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/operator_launch.json`,
  SHA-256
  `b429d7afa6e22fcb69531fe9e938c04483be89e74561d242afc0141cc9837f9d`.
  Its materialized plan records Job 1 as zero-render and Jobs 2/3/4 as
  5/4/2 cold legs.
- Final operator transport receipt:
  `results/h3_music_followup_campaign/operator_logs/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001-operator-001/launch.json`,
  SHA-256
  `13946e258890c59da23715887de824f08a25b66cab65e186a6af1d2409057bdd`.
  It records `transport_status: FAILED`, child exit code 1, the same terminal
  lifecycle hash, and no force, kill, server adoption, or transport-side GPU
  cleanup attempt. The preflight receipt SHA-256 is
  `e55390de8216dd76de7e9172b534d1dafeb77fe685b7b801aa8676d634a1ae1a`.
- The terminal lifecycle row preserves the exact reason: receipt invariant
  drift on `h3_music_followup_score_seed42_f277`, where `gate_pass` was false
  and receipt status was `FAIL (VRAM 14.72 GB > 14.5 GB)`. Its final-state
  snapshot records no `.gpu.lock`, `.suite.lock`, `.server.pid`,
  `.server.idle-gate.json`, `.queue.quarantine.json`, or port-8199 listener.
  The final artifact and receipt bytes were preserved.
- All 11 Manager logs contain exactly one `network_mode: offline` at line 106,
  before `got prompt` at line 142, followed by one `Prompt executed in` at
  line 191. Their exact hashes are bound per leg below.

## Job 1 - topology A/B local-schema finding

The origin receipt binds obsolete recipe SHA-256
`599718d4ee5b1a04309a4352cded8167c4e51075a9f858bdbf3468a53aae6a4e`,
but those exact recipe bytes were not found in the audited worktree,
reachable revisions, or unreachable Git blobs. The closest recoverable nested
source is not byte-identical to that pinned origin recipe and was retained as
metadata only.

An in-memory structural reconstruction of the old nested `ref_images` shape
was rejected before server boot or prompt submission by the current local
`run_recipe.py` schema validator. The exact rejection was:

> Node 7 (MiniMaxH3ReferenceToVideo) input 'ref_images' is a nested V3 autogrow container that ComfyUI ignores; use direct dotted sockets such as 'ref_images.ref_image_0'

This is an enforced local lab-runner schema result under the installed V3
socket contract. It is not a MiniMax node runtime error and does not prove an
audio regression. Job 1b therefore had zero render legs.

The structural comparison possible from available evidence is:

- Historical nested shape: `ref_images: {ref_image_0: ["11", 0]}`.
- Current accepted flat-V3 shape:
  `ref_images.ref_image_0: ["11", 0]`, with nested `ref_images` absent.
- In the reconstructed and current structures, the visible native-audio
  branch remains
  `SamplerCustomAdvanced -> VAEDecodeAudio -> CreateVideo.audio`.

Because the exact historical recipe bytes are absent and the old socket shape
is unreachable through this runner, there is no valid output A/B and no
causal claim about the socket migration. The Job 1b recovery condition was
not reached, so no bonus leg was authorized or rendered.

## Render receipt and artifact ledger

All rows are exploratory single cold legs in the Sage-free,
Manager-offline, `--disable-pinned-memory`, reserve-12 GiB lane with per-leg
`--shutdown`. `Abs/base/net` are receipt fields in GiB; net is each leg's own
absolute peak minus its own prequeue baseline. `EB` means the receipt contains
the exact stamp `elevated-baseline lane, operator-authorized 2026-08-10`.
For every row, `results/<recipe>_run1.json` and its
`results/<recipe>.json` latest alias are byte-identical; the listed receipt
SHA-256 applies to both files.

| # | Cell; seed / frames | Machine gate; abs / base / net GiB; wall | Receipt SHA-256 | Native-audio artifact evidence | Recipe SHA-256 | EB | Manager log SHA-256 |
|---:|---|---|---|---|---|:---:|---|
| 1 | Job 2a; 42 / 124 | met (cold); 8.145 / 1.826 / 6.319; 970.3 s | `c0c4d3ad589550f9b47df7909863fabb553638d89ed5b13f912600c01861128b` | 852,550 B; 5.167 s audio; `c69136470497dd745d728dee39fce06e02e3059dffa6686f1f2b28c286d409b4` | `6da9e9bd1f10c70c097f8e5c4dd5a6ba2ee73f5259d74d65684cd49cabfdf9c9` | no | `4f1a7ef44c8ea9c98274bbe054429b47f01581b74cc401ff08e62d66a0d0a8ff` |
| 2 | Job 2b; 42 / 124 | met (cold); 8.210 / 2.134 / 6.076; 980.5 s | `d9e489a0edb3a76ac65651571325135e94fd30158a8e97d018f6cd6ded6baa53` | 796,775 B; 5.167 s audio; `a27571f53ef3ed56cfa71a8842ce872d1026af845fcbcc579c6f4159536d8590` | `f190104d94542abe26097013f534f01f8d012c7fa48da3c95be6d45a489fdac6` | yes | `6e863c9ab70857038bc3315df0acccbaead9e9fda8b5c5be076c1567a1f8a466` |
| 3 | Job 2c; 42 / 124 | met (cold); 8.352 / 2.082 / 6.270; 998.9 s | `9132e51e2da87d68c0e55bdb9c317e66f06b717369b5779444ee1d93f0cd1eb7` | 1,264,233 B; 5.167 s audio; `deec6cd75788babea05a78be8f437b3a00f0bf030a3209a978cfbe36f5128ca4` | `849a764e8b5da7ffaac8e4ffea91b7d152f05193d6a860fab8ae36049a70c2e1` | yes | `35d77eb0dbb8087f81d1f70053325d68e51e119e4838220888f83b2dfefac6ab` |
| 4 | Job 2d; 42 / 124 | met (cold); 8.266 / 2.259 / 6.007; 976.0 s | `a45b9b93db9f4c9b19ce514f8a7e1a54992b8cfa028d9c7581061925b78b17c6` | 1,255,885 B; 5.167 s audio; `bc1acf344b2d836df049fedfb97c7172df8740d6bf3bfa35997abedc6df07bb5` | `199eba02e117eb51ceb26949ce5433e7cafb8d8a3baa7dfce1193f335c62cd4e` | yes | `f9979d1ab96c96432119bdea4203d388a7ff4f20f43293afb42203d5fa52c2b4` |
| 5 | Job 2e; 42 / 124 | met (cold); 8.406 / 2.305 / 6.101; 990.5 s | `9589e34bf32da38551457a5c6178f5ecafde1aa03d0d67140feab42c6fa2fb1d` | 799,356 B; 5.167 s audio; `f964919a8f1256f59de409a98591d7f966fa6ce17f75b358cee179136cf2c76c` | `589217f02f200b994dff416dc7b9db3c426155fae38b131f437499959f032520` | yes | `c4c7cb152d1a96b324c1ae07e744404d51d9e40a64d748170e44de6e6d0b4c32` |
| 6 | Job 3 seed 43; 43 / 124 | met (cold); 8.373 / 2.143 / 6.230; 942.9 s | `98809e97d496faceac359acefce193fe42003792d664961328f6908446248f02` | 973,423 B; 5.167 s audio; `548398444eef561df09ba81e6d127712c92f0cf10b97d5c7a77e1bac38effe2d` | `4ee5e5afe067704f84c8a62555499e55f6064b0e490345cb07eb53fdbd2271f6` | yes | `0a0020dff9fb7b5e789acff36db5c0382176ac4903d5778d2c46117c223693a2` |
| 7 | Job 3 seed 44; 44 / 124 | met (cold); 8.049 / 2.127 / 5.922; 888.9 s | `81ebf5c9276e44095a76da12b882f0933ceca3280fa2f01a6f58dacaa6df61f5` | 1,049,845 B; 5.167 s audio; `5dd92fe9968a4bc4c2742554c7ef19aea5f32d3eacedeccb2816dd620e2dbacf` | `dc897f660680c0c5a004266d3388b8fc6d2b6207317dc009ccaf5e8f42e36bed` | yes | `6d4d04d74a38c6c7f5eadcf8dfbdd3440c79a54f1353eb313e32e4b188cf2405` |
| 8 | Job 3 seed 45; 45 / 124 | met (cold); 8.163 / 2.127 / 6.036; 901.4 s | `5720807ffb679aef64a980d753e40eb29fdc9d2904448b68a9baa57474de001e` | 1,050,036 B; 5.167 s audio; `1363819a595b96d39263e0c402cdbcc7b2ac7e60b07978f5203443c72d0f05c9` | `78fe70e46930652d83d5c6312b2b90cd2f847d2e2fc2dae2e8945f83cf9a52b9` | yes | `c886f6d812dd2b4b28b6fb7eec739a4a925d49456c8b795ac79fe8a5bdd5bb63` |
| 9 | Job 3 seed 46; 46 / 124 | met (cold); 8.129 / 2.236 / 5.893; 902.7 s | `43a0367c2e0050f379b837c71a71fabbd85501ebdd40e3c37f324dfe88c1adfc` | 1,065,739 B; 5.167 s audio; `04cd26a8b52b02b4f8dc618becefb85b5fcacc5d5216e35c186d8069c9fc082c` | `045ad26f7ad8de5b8e6d37b76af260912692991c8565bf25c30d6209d65372ae` | yes | `3c8ae61b463afd9ded1f548d3726911e0e7258d30318afcb3336b65855a5424f` |
| 10 | Job 4 f192; 42 / 192 | met (cold); 11.063 / 2.238 / 8.825; 1,863.9 s | `7c5857736bda672e92507260acbf6a6782c48d4287a201134a352ae164234feb` | 1,556,143 B; 8.000 s audio; `dba434bd6d3ef854d3e723b58f5d0f2921574d3b7cdfecc7ab754f331b7996f2` | `29589d9bf565310da7352e9623c5b064189d106703a3ee95a50eb9b801a04c9d` | yes | `573adec87d61f5da0989cc4f9a85a605032b734715a3bc1271a0f5f0007eca4c` |
| 11 | Job 4 f277; 42 / 277 | **hard gate exceeded**; 14.722 / 2.239 / 12.483; 3,594.7 s | `5b7e8963c464dc8bcf23accc1cda120234bfd0ea8614eeb885d6f8c3f1cd1124` | 2,310,113 B; 11.542 s audio; `727c2bbbf3ec969ebf8051b7659f0cd7531fba07abfb52340baf9aa1b2c60a67` | `8965353ccf49d075f953cf9700119cb4030cface2b909f235d3a7bc8fd739094` | yes | `c76fc23d2e7ca699d9a7c514d96f07307f7569cc350539041fd33168994f8df4` |

The exact elevated-baseline stamp is absent from row 1 because its baseline is
1.826 GiB. It is present verbatim in rows 2 through 11 because each baseline
is strictly above 2.0 GiB. No campaign baseline exceeded the 3.0 GiB advisory
marker. Cold/warm drift is not applicable because this campaign contains no
same-identity warm legs.

## Machine descriptor table

The pinned analyzer is
`scratch/h3_music_machine_descriptors/analyze.py`, SHA-256
`24cc09b0a7a187d7cf7a5dee0ab5547ad4b8bf64d40641ace86c1c8f571a5b3f`;
the in-campaign manifest wrapper used for D01-D10 has SHA-256
`5d805d411751b855d4e9d971bca88afd2e439950b0248fe13f708c23152023f5`.
For each `Dxx` citation below, the cited `descriptors.json` record contains the
exact executable paths and input path in its `commands.C0_probe` through
`commands.C5_scene_scores` strings:

- C0: stream/duration probe.
- C1: ffmpeg `ebur128=peak=true` for integrated LUFS, LRA, and true peak.
- C2: ffmpeg `silencedetect=noise=-40dB:d=0.2`.
- C3: ffmpeg `astats=metadata=0:reset=0`.
- C4: ffmpeg extraction to mono 48 kHz signed 16-bit PCM; the pinned NumPy
  analyzer computes centroid, flux, periodicity, and band ratios from it.
- C5 plus C4: ffmpeg scene-score buckets plus PCM RMS for the crude
  motion/audio Pearson correlation. It is an alignment proxy, not sync proof.

`RMS`, `flat`, and `peaks` are left/right channel values. `Bands` are
low/mid/high energy ratios for 20-250 Hz, 250-2000 Hz, and 2000-24000 Hz.
Machine descriptors do not determine music presence, mood, quality,
usability, or causation.

| # | Cell | LUFS / LRA / TP dBFS | Silence count / s | RMS dBFS L/R | Flat L/R; peaks L/R | Centroid mean +/- std Hz | Flux | Periodicity score @ lag s | Bands L/M/H | Motion/audio r | Source; human judgment |
|---:|---|---|---|---|---|---|---:|---:|---|---:|---|
| 1 | Job 2a | -25.9 / 0.8 / -13.3 | 0 / 0.000000 | -30.113689 / -27.366368 | 0 / 0; 2 / 2 | 1103.196531 +/- 176.342059 | 0.201673 | 0.136090 @ 0.367667 | 0.263638 / 0.723858 / 0.012504 | -0.470183 | D01 C0-C5; PENDING_HUMAN |
| 2 | Job 2b | -30.2 / 4.4 / -19.5 | 0 / 0.000000 | -33.967569 / -33.365508 | 0 / 0; 2 / 2 | 1204.390666 +/- 204.824406 | 0.179329 | 0.461584 @ 0.254563 | 0.653014 / 0.302267 / 0.044718 | -0.364487 | D02 C0-C5; PENDING_HUMAN |
| 3 | Job 2c | -21.6 / 0.1 / -9.7 | 0 / 0.000000 | -25.858698 / -22.679784 | 0 / 0; 2 / 2 | 953.845600 +/- 129.357349 | 0.165099 | 0.249052 @ 0.299917 | 0.317279 / 0.671003 / 0.011718 | 0.370013 | D03 C0-C5; PENDING_HUMAN |
| 4 | Job 2d | -32.5 / 3.9 / -21.7 | 2 / 0.974094 | -36.729963 / -36.448856 | 0 / 0; 2 / 2 | 1519.845945 +/- 211.343010 | 0.235131 | 0.319230 @ 0.254604 | 0.315249 / 0.605678 / 0.079073 | -0.183361 | D04 C0-C5; PENDING_HUMAN |
| 5 | Job 2e | -16.6 / 0.5 / -3.1 | 0 / 0.000000 | -20.549976 / -18.379284 | 0 / 0; 2 / 2 | 923.256590 +/- 213.596462 | 0.299808 | 0.233884 @ 1.004833 | 0.110121 / 0.881054 / 0.008825 | 0.001555 | D05 C0-C5; PENDING_HUMAN |
| 6 | Job 3 seed 43 | -19.7 / 2.9 / -12.1 | 0 / 0.000000 | -22.654509 / -22.621460 | 0 / 0; 2 / 2 | 704.353203 +/- 101.845957 | 0.156501 | 0.202191 @ 0.687771 | 0.006179 / 0.993766 / 0.000055 | -0.457314 | D06 C0-C5; PENDING_HUMAN |
| 7 | Job 3 seed 44 | -15.3 / 2.1 / -8.0 | 0 / 0.000000 | -17.882067 / -17.703820 | 0 / 0; 2 / 2 | 665.397058 +/- 41.863130 | 0.158001 | 0.411977 @ 0.309063 | 0.010071 / 0.989875 / 0.000053 | 0.194493 | D07 C0-C5; PENDING_HUMAN |
| 8 | Job 3 seed 45 | -19.5 / 0.5 / -10.4 | 0 / 0.000000 | -21.522418 / -22.452535 | 0 / 0; 2 / 2 | 607.945044 +/- 110.742770 | 0.193246 | 0.205392 @ 0.336313 | 0.187665 / 0.812217 / 0.000118 | -0.296306 | D08 C0-C5; PENDING_HUMAN |
| 9 | Job 3 seed 46 | -18.4 / 1.5 / -8.1 | 0 / 0.000000 | -20.974990 / -20.974611 | 0 / 0; 2 / 2 | 690.944835 +/- 130.991311 | 0.183431 | 0.193588 @ 0.377583 | 0.165206 / 0.834745 / 0.000049 | 0.283513 | D09 C0-C5; PENDING_HUMAN |
| 10 | Job 4 f192 | -22.3 / 1.1 / -12.9 | 0 / 0.000000 | -24.339488 / -24.927812 | 0 / 0; 2 / 2 | 781.536860 +/- 116.311570 | 0.223106 | 0.127792 @ 0.637750 | 0.332419 / 0.667132 / 0.000449 | 0.035733 | D10 C0-C5; PENDING_HUMAN |
| 11 | Job 4 f277 | -13.9 / 5.6 / -5.0 | 0 / 0.000000 | -16.143498 / -16.424216 | 0 / 0; 2 / 2 | 870.144714 +/- 221.546079 | 0.160236 | 0.217184 @ 0.275188 | 0.139537 / 0.860302 / 0.000162 | -0.249160 | D11 C0-C5; post-terminal scratch only; PENDING_HUMAN |

The f277 artifact exists and its receipt reports native audio, but the hard
gate stopped the coordinator at receipt validation before its descriptor
phase. D11 was generated afterward from the preserved artifact in a separate,
render-free, scratch-only analysis. It is a valid machine measurement with
`certification_effect: false`; it does not amend the terminal lifecycle, turn
the source gate green, or imply that the campaign itself completed row 11's
descriptor phase.

Descriptor record citations:

- D01:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o01-h3_music_followup_mood_dim_lighthearted_seed42_f124/descriptors.json`,
  SHA-256
  `37d32e0f6c1f5bfe2db80bea22f2180ecdacc8836615f2833838ed3db45eaf73`.
- D02:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o02-h3_music_followup_mood_dim_tense_seed42_f124/descriptors.json`,
  SHA-256
  `61f0aa24b8a3bfb2a89aca9144cd24602ecdf7b4900fd2750b63f39e8709d81c`.
- D03:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o03-h3_music_followup_mood_bright_lighthearted_seed42_f124/descriptors.json`,
  SHA-256
  `7c3a2fa1bf96bb765e752b0e9a8908324f5746f4e3ec733cd04ce3620a411ed3`.
- D04:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o04-h3_music_followup_mood_bright_noir_seed42_f124/descriptors.json`,
  SHA-256
  `f0020d86abcc9709f3f4d844f7d610d7d9467f3c6cb16b348b6924a20a20e301`.
- D05:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o05-h3_music_followup_mood_dim_ragtime_seed42_f124/descriptors.json`,
  SHA-256
  `b0935c5f4a3723657759d26c286872753e0e5345f8819ca1eb7b0b5d1bde29cc`.
- D06:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o06-h3_music_followup_score_seed43_f124/descriptors.json`,
  SHA-256
  `aac36302c8bafa6d839741021d4130c3736ca6bd4e2b61f44a846256b195f6ea`.
- D07:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o07-h3_music_followup_score_seed44_f124/descriptors.json`,
  SHA-256
  `5ed096df705efac3e346d68093d179eb0a07ba95bb53fe7a08a10d1e3a4a81c0`.
- D08:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o08-h3_music_followup_score_seed45_f124/descriptors.json`,
  SHA-256
  `a196d0c9ca879f4a8d1f5364092dbea1fc695539fa73fbbddcaa2b3f47cca8d9`.
- D09:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o09-h3_music_followup_score_seed46_f124/descriptors.json`,
  SHA-256
  `93645accc0a73b9c72e4ed8392ef50b4c5c8af5f3901bd6d3d5da33c9cce1011`.
- D10:
  `results/h3_music_followup_campaign/campaigns/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001/descriptors/o10-h3_music_followup_score_seed42_f192/descriptors.json`,
  SHA-256
  `7e27dabd6bc492cd8ea530288363cc7f0b65634694c391777a3298bfe80e973b`.
- D11, explicitly post-terminal and noncertifying:
  `scratch/h3music-followup-20260810T195909Z-ac3f65ee-attempt-001-f277-post-terminal-descriptors/descriptors.json`,
  SHA-256
  `1e218991a0f3ee87ad2bf99d5127d6be6c3bfcf38ea62540cbcb5c169d4c6a1c`.
  Its scratch-only wrapper
  `scratch/analyze_h3_music_followup_f277_post_terminal.py` has SHA-256
  `9a8ecded669e7cf96e72f23c13dd484b2d3c2167146017a30e3cde05f3c45995`;
  its verification receipt has SHA-256
  `4fc40ec655068906340cf73318557409a660663b74556b9a16ef2ca2c602bd5f`.

## Listening questions

### Job 1 - origin-topology question

The initial campaign produced no Job 1 clip. A later, separately authorized
prompt-only origin addendum completed below; its eye/ear comparisons remain
**PENDING_HUMAN**.

**Operator VISUAL ruling on the origin addendum clip (2026-08-10):**
"cinematic, no real facial or body movement, just 3D pan" - consistent with a
camera-only prompt and no reference subject. Note the measurement: 6.438 GiB
absolute / 4.328 GiB net, the LIGHTEST H3 configuration ever measured in this
lab.

**Operator EAR ruling (2026-08-10): "music was OK - dramatic, maybe not crazy
sci-fi dramatic, but it worked in time with the pan."** The ORIGIN QUESTION IS
CLOSED: prompt-only generation produces usable, scene-synced music at the
lab's lightest H3 cost, but does NOT recover the origin clip's remembered
magic. Verdict on the mystery: the woman-clip's quality was seed-and-moment
luck on an unreproducible wiring shape, not a recoverable mode. No topology
work is pursued. The production design stands as ruled: the score-request
path (5-of-5 human pass) is the music lane's primary mode; prompt-only is a
valid budget variant (~4.3 GiB net, "OK dramatic" grade) for undemanding
interstitials. This was the last PENDING_HUMAN item in the campaign.

### Job 2 - words versus scene

**RULED by Jeffrey 2026-08-10: "honestly they all look good... music is good
in all - if that's what the script beat calls for."** All five mood cells
produced usable scores; the moods differentiate enough that selection is a
SCRIPT decision, which ratifies the standing design rule: the score request
is derived from the beat's dramatic intent, never boilerplate. Motion notes:
2a and 2c have good motion.

### Job 3 - score-prompt seed sweep

**RULED: GREAT - effectively 5 of 5.** Seeds 43-46 all usable (plus seed 42's
melancholy score from the prior study, usable for a lighter beat). Visual
caveat: seeds 45 and 46 are "just pans, not real movement" - an audio PASS
with a motion note, feeding the same motion-prompting lesson as the ladder.

### Job 4 - duration behavior

**RULED: survives.** The 11.5 s clip has MORE movement than the shorter ones,
music holds. Machine caveat stands: f277 measured 14.722 GiB absolute (over
the 14.5 gate) on this lane - production lengths above f192 need headroom
work before they are routine; f192/8 s is comfortably inside (11.06).

### Origin/topology production recommendation

**HOLD - PENDING_HUMAN** for any origin/topology production change. Jobs 2–4
already have the operator rulings above. This report authorizes no dropdown,
prompt-builder, topology, production, or OTR change. OTR remains out of scope
and untouched.

## Driver synthesis (2026-08-10) — historical pre-run hypothesis

The Job 1 schema rejection carries the key fact in its own wording: the old
nested `ref_images` container "is a nested V3 autogrow container that
**ComfyUI ignores**". If the origin render's reference image was silently
ignored, the origin clip was effectively PROMPT-ONLY generation - which
explains, in one stroke, (a) why an unprompted WOMAN appeared instead of the
referenced man, and (b) why its audio behaved unlike every properly
picture-conditioned run since. Under this reading there is no audio-branch
wiring regression at all: the variable is REFERENCE CONDITIONING itself -
conditioning the picture tightly may be what suppresses the free musical
behavior the operator loved.

DECISIVE CHEAP TEST (then queued; completed in the addendum below): render the
EXACT origin prompt text with NO image input at all (and optionally the same
at t2v vs ref-less r2v if both paths exist), seed-matched, f124, standard
reserve lane. If music returns without a reference image, the origin behavior
is recovered, the "topology regression" is closed as a misread, and the music
lane's design becomes: prompt-only (or lightly-conditioned) generation for
scored interstitials.

Also noted for the envelope campaign: Job C's 15.390 GiB absolute (net 13.064)
first cell ran WITHOUT the reserve-pressure lane every certified H3 number
used (this campaign's f124 legs net ~6.0-6.3 under reserve-12gb). Per the
lab's own Rule 12, unpressured allocation is greedy and is not the floor.
The subsequent operator ruling skipped the Job C rerun. Job D instead
completed from a separately authorized standalone cold source on the standard
reserve lane, as documented in `ENVELOPE_LADDERS.md`.

## Prompt-only origin test — 2026-08-10

The decisive primary test is complete. It used seed 42, 832×480, 124 model
frames at 24 fps, native sampled audio, and the exact historical prompt text:

> Use &lt;Picture 1&gt; as the exact character identity and appearance reference. Place that person in a vintage radio control room under warm analog lighting; preserve their face, hair, clothing, and proportions while the camera makes a slow cinematic move.

The Ref2VA graph had no `LoadImage` node and no image, audio-reference, or
video-reference socket connected. The node accepted the dangling
`<Picture 1>` text and rendered normally, so the conditional no-tag fallback
was not authorized and did not run. This confirms the narrow technical fact
that the current node can execute this exact prompt with no picture
conditioning; it does not determine what the clip sounds or looks like.

The immutable cold receipt is
[`h3_music_followup_origin_prompt_only_exact_seed42_f124_run1.json`](../results/h3_music_followup_origin_prompt_only_exact_seed42_f124_run1.json),
SHA-256 `f425e697cf52bf85cae915cafaeebdba3750a4b95b4c3fa3794846a8ea416545`.
The exact no-image recipe SHA-256 is
`c877d6db69aad72b9f5b9333e80d53e4d35deecd09d85192b6d4345c76100428`.
It records a 2.110 GiB immediate pre-queue baseline, 6.438 GiB absolute peak,
4.328 GiB net peak, and 192.5 s wall time. The baseline therefore carries the
exact `elevated-baseline lane, operator-authorized 2026-08-10` stamp. This is
one cold machine-gated exploratory leg only: `pass=false`, `warm_pass=false`,
and it has no certification or promotion effect. The 498,826-byte native-A/V
artifact is
[`h3_music_followup_origin_prompt_only_exact_seed42_f124_out_00001_.mp4`](../outputs/h3_music_followup_origin_prompt_only_exact_seed42_f124_out_00001_.mp4),
SHA-256 `1ea55eb6e0dc846ae6b5f190dfe0ed835fb296639a572d870e4b2420176368cd`.
The Manager log proves `network_mode: offline` at line 106 before the first
prompt at line 142, and owned shutdown left the lab clean. The operator launch
receipt is
[`launch.json`](../results/h3_short_jobs/operator_logs/h3short-origin-20260811T010927Z-4afb7491/launch.json),
SHA-256 `022396b12d040ac51e4ef2aa0322d79c388493ff6e4ec8f7b4f39975a251529c`.

The pinned CPU-only analyzer output is
[`descriptors.json`](../scratch/h3short-origin-20260811T010927Z-4afb7491-descriptors/descriptors.json),
SHA-256 `261734f06e941e12144c9a0f6c0a8d88366129a5b5808d99fa1e54aa00b9f148`.
It is receipt-bound to the exact artifact and preserves
`quality_judgment=PENDING_HUMAN`.

| Integrated loudness | LRA | True peak | Silence | Centroid mean ± std | Flux | Periodicity | Low / mid / high energy | Scene-score/audio-RMS r |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| -29.1 LUFS | 5.1 LU | -16.9 dBFS | 0 intervals / 0.0 s | 994.349 ± 91.878 Hz | 0.128154 | 0.716514 at 0.265313 s | 0.226638 / 0.765574 / 0.007788 | 0.129694 |

These descriptors do not establish music presence, mood, quality, usability,
or causation. `PENDING_HUMAN`: whether this clip resembles the remembered
origin clip, whether it contains music, what is visible, and whether removing
picture conditioning is useful for scored interstitials. No production,
prompt-builder, dropdown, topology, or OTR change is authorized by this test.

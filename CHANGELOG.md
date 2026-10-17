# Changelog

All notable changes to Touhou Tagger are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
New entries are kept under **Unreleased** until a release, then moved into a
dated version heading. Group user-visible changes under Added, Changed, Fixed,
Removed, or Security; do not use this file as a commit-by-commit log.

## Unreleased

### Added

- `japanese_romanizer.explain_romaji()`: romanizes a title and reports, per
  word, where its reading came from (reviewed title/phrase/loanword table,
  numeral rule, UniDic etymon spelling, or the dictionary) together with
  plain-language review reasons: a kanji reading guessed outside the
  dictionary, a word read as a person's name although the dictionary also
  knows it as something else, or a run of kanji read one by one. Reviewed
  replacements are never flagged. `romanize_file()` results now carry the
  same `review` list, the Romanise log prints a `review:` line under such
  tracks, and the per-album summary counts them, so QC can be aimed at the
  titles that were partly guessed instead of every title.

- "Force overwrite staff tags" (GUI checkbox; `--force-credits` on the CLI):
  makes the wiki authoritative for `arranger`, `vocalist`, and `lyricist`
  instead of preserving whatever the file already has, so a re-run can
  correct credits written by an earlier release. A credit the wiki already
  agrees with is still skipped, and a role the wiki does not credit is left
  alone rather than cleared.
  The checkbox is greyed out when no staff tag is selected.
- `source/retag_credits.py`: migration CLI that repairs `arranger`,
  `vocalist`, and `lyricist` tags already written with the artist's circle.
  It re-fetches each album from THBWiki rather than reversing the faulty
  mapping, which is not invertible. Dry run by default, checkpointed per
  album so an expired THBWiki session can be resumed. It rewrites a tag only
  when the tag both disagrees with the wiki and matches the old bug's output
  exactly. On an expiry the run pauses for the session to be re-verified and
  retries the same album, so one invocation can span several sessions;
  `--no-wait` stops instead, as does any run without a terminal on stdin.

### Changed

- Address honorifics are written hyphenated after the name instead of fused
  into it: 霊夢さん → Reimu-san, まりさちゃん → Marisa-chan, 神様 → Kami-sama,
  影狼殿 → Kagerou-dono. Covers さん, ちゃん, くん/君, さま/様 and 殿 as nominal
  suffixes; lexical words such as 赤ちゃん and 地霊殿 are unaffected.
- A hiragana word next to a katakana word can no longer be fused with it
  while the romanizer tries a katakana reading of the hiragana (スナックさなえ
  was Sunakkusanae, now Snack Sanae). The original spelling is never cut,
  so mixed-script words such as ヤバい keep their dictionary reading. A
  katakana candidate that would cut an unknown word across a reviewed
  spelling is also rejected (ぬえの stays Nue no).
- Old-form (kyūjitai) and variant kanji are analyzed through their modern
  forms, so 天體觀測 reads Tentai Kansoku instead of Ten Tei Kan Soku and
  幻想鄉 is no longer left unresolved; the title's own spelling is
  unchanged. The modern form is used only when it parses into fewer or
  fewer-unknown words, so a word the dictionary already knows in its old
  form keeps its reading. 龍 and simplified Chinese forms are not mapped.
- A long-vowel mark that can only be a dash (at the start, after a space,
  punctuation or Latin, between two kanji, or closing an earlier dash) is
  written as a hyphen, so titles such as 夢 ー終焉ー get a sort key instead
  of being skipped as unresolved. A mark after kana is always a long vowel.
- Romanization joins compounds the dictionary splits into short units: a
  prefix now merges with the word it modifies (大妖精 → Daiyousei, 無条件 →
  Mujouken, 超新星 → Choushinsei) as suffixes already did, and a word whose
  reading is the rendaku form of its own lemma joins the element before it
  (無縁塚 → Muenzuka, 三途川 → Sanzugawa, ほたる囃子 → Hotarubayashi).
  The ordinal 第 stays its own word (Dai 8 Ban, Dai Ichininsha).
- A two-kanji Sino-Japanese noun is no longer read as a surname when the
  dictionary's common-noun entry is clearly the more frequent word, so 東方
  in titles the override tables do not cover reads Touhou instead of Toubou
  or Higashikata. Names that are themselves the frequent reading (西行,
  望月, 千秋) are untouched.

- Japanese title romanization now reads recognized number/counter expressions
  as complete words, including Arabic-written forms such as `2人` → `Futari`.
  Standalone numbers and Latin identifiers keep their spelling.
- Per-track `arranger`, `vocalist`, and `lyricist` tags now follow the same
  romanization resolver as the sort fields, so TouhouDB's official name is
  used where it has one. TouhouDB remains opt-in; without it the credits keep
  the wiki's original names.

### Fixed

- Romanizer title overrides also match delimited titles in annotations;
  reviewed Japanese spelling aliases handle selected Chinese character
  variants without globally converting Chinese text. Added supported rare
  readings and preserved intentional `〇` masking inside Japanese words.
- Romanizer file tagging now assumes Japanese for Han-only titles, with
  explicit Chinese title/directory exclusions and Chinese-language markers
  preserving existing tags. Reviewed Chinese soundtrack directories are
  excluded without inferring language from artist nationality.
- Reviewed Chinese titles can also be excluded within a specific circle/album
  directory pair, including disc subfolders. The unresolved-title review adds
  matches covering 421 recorded files across 41 release entries while keeping
  Japanese neighbors and the same titles on other releases eligible.
- Incomplete title romanizations containing Han/kana characters are now
  reported as unresolved and never written to `titlesort`, even with force
  overwrite. Known Japanese and simplified-Chinese title spellings for
  `少女綺想曲`, `二色蓮花蝶`, and `有頂天変` have explicit reading overrides.
- The explanatory contraction `なんだ` now joins as `Nanda`, keeping final
  particles separate (`なんだよ` → `Nanda yo`). The rule requires matching
  grammatical tokens and preserves explicit gaps and reviewed replacements.
- Classical adjective endings such as `儚き` now join as `Hakanaki` when
  MeCab splits an adjective stem from a directly adjacent hiragana `き`.
  The repair does not cross whitespace, punctuation, or reviewed replacements.
- Romanization preserves surface readings such as `あたし` → `Atashi` and
  `やっぱり` → `Yappari`, handles counter sound changes, and joins small-っ
  and syllabic-ん boundaries using readings instead of written kanji.
- Stylized kana analysis retains particles and expressive long vowels;
  standalone katakana letters are no longer converted indiscriminately.
  Extended kana combinations and half-width/rare-kanji detection are covered
  consistently, and pykakasi fallbacks use the same Hepburn rules while
  preserving characters the fallback cannot read.
- Per-track `arranger`, `vocalist`, and `lyricist` tags no longer show the
  artist's circle instead of the artist. THBWiki's Staff section lists
  `[Artist, Circle, Tracks]`, and the second column was being read as a
  romanization of the first, so credits were rewritten to the circle
  (`3L` → `NJK Record`, `Shibayan` → `ShibayanRecords`). Compilation albums
  that draw one track from each of many circles were affected worst. The
  same mapping fed `artistsort` and `albumartistsort`.

## 0.1.0 - 2026-08-05

### Added

- Initial public-release preparation: user documentation, pinned dependency
  groups, offline regression tests, and continuous integration (Linux, with a
  Windows job for regression coverage).
- Touhou album tagging sourced from THBWiki, with optional English Touhou Wiki
  lookup and optional Japanese-title romanisation.
- GUI and command-line workflows, including dry-run previews and optional CUE
  album-image splitting.

### Security

- Manual THBWiki authentication and optional browser-cookie auto-pull are
  documented; browser cookies are not stored in project files or configuration.

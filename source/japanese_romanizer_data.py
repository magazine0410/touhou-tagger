# -*- coding: utf-8 -*-
# Shared data for japanese_title_to_romaji.py and japanese_title_to_romaji_full.py

_LOANWORDS: dict[str, str] = {

    # --- Touhou Project: characters ---

    # PC-98
    "sarieru":        "Sariel",
    "gurimoa":        "Grimoire",

    # Embodiment of Scarlet Devil
    "arisu":          "Alice",
    "remiria":        "Remilia",
    "furan":          "Flan",
    "furandooru":     "Flandre",
    "sukaaretto":     "Scarlet",
    "pachuri":        "Patchouli",
    "pachori":        "Patchouli",
    "chiruno":        "Cirno",
    "ruumia":         "Rumia",
    "koakuma":        "Koakuma",
    "meirin":         "Meiling",

    # Perfect Cherry Blossom
    "retihowaitorokku": "Letty Whiterock",  # sometimes appears as one token
    "reti":           "Letty",
    "howaitorokku":   "Whiterock",
    "runasapurizumuribaa": "Lunasa Prismriver",
    "meruranpurizumuribaa": "Merlin Prismriver",
    "ririkapurizumuribaa": "Lyrica Prismriver",
    "runasa":         "Lunasa",
    "meruran":        "Merlin",
    "ririka":         "Lyrica",
    "purizumuribaa":  "Prismriver",
    "youmu":          "Youmu",
    "yuyuko":         "Yuyuko",
    "saigyouji":      "Saigyouji",
    "bukureshuti":    "Bucuresti",

    # Imperishable Night
    "eirin":          "Eirin",
    "kaguya":         "Kaguya",
    "mokou":          "Mokou",
    "reisen":         "Reisen",

    # Mountain of Faith / Subterranean Animism
    "kanako":         "Kanako",
    "suwako":         "Suwako",
    "sanae":          "Sanae",
    "satori":         "Satori",
    "koishi":         "Koishi",
    "rin":            "Rin",
    "utsuho":         "Utsuho",
    "kisume":         "Kisume",
    "yamame":         "Yamame",
    "parusui":        "Parsee",

    # Undefined Fantastic Object / Ten Desires / etc.
    "nue":            "Nue",
    "byakuren":       "Byakuren",
    "murasa":         "Murasa",
    "ichirin":        "Ichirin",
    "shou":           "Shou",
    "nazrin":         "Nazrin",
    "mamizou":        "Mamizou",

    # Imperishable Night (additional)
    "riguru":         "Wriggle",
    "rooreraii":      "Lorelei",

    # Phantasmagoria of Flower View
    "medisun":        "Medicine",
    "merankorii":     "Melancholy",

    # Legacy of Lunatic Kingdom
    "kuraunpiisu":    "Clownpiece",
    "hekaatia":       "Hecatia",
    "rapisurazuri":   "Lapislazuli",
    "doremi":         "Doremy",
    "sagume":         "Sagume",

    # Hidden Star in Four Seasons
    "raaba":          "Larva",
    "nemuno":         "Nemuno",

    # --- Touhou Project: places ---
    "shanhai":        "Shanghai",
    "gensokyou":      "Gensokyo",
    "koumakan":       "Koumakan",
    "koumakyou":      "Koumakyou",
    "hakurei":        "Hakurei",
    "makai":          "Makai",
    "eientei":        "Eientei",

    # --- Touhou Project: music terms appearing in song titles ---
    "voiru":          "Voile",
    "runa":           "Lunar",
    "daiaru":         "Dial",
    "tepesu":         "Tepes",
    "seputetto":      "Septette",
    "erufu":          "Elf",
    "porutaagaisuto": "Poltergeist",
    "nekurofantajia": "Necrofantasia",
    "fantajia":       "Fantasia",
    "fantomu":        "Phantom",
    "fantazumu":      "Phantasm",
    "marugatoroido":  "Margatroid",
    "purizumu":       "Prism",
    "daiyamondo":     "Diamond",
    "kurisutaru":     "Crystal",
    "etaniti":        "Eternity",
    "rabirinsu":      "Labyrinth",
    "iryuujon":       "Illusion",
    "vanpaia":        "Vampire",
    "misutia":        "Mystia",
    "sutaa":          "Star",
    "sani":           "Sunny",
    "muun":           "Moon",
    "majikku":        "Magic",
    "mirakuru":       "Miracle",
    "supuringu":      "Spring",
    "uintaa":         "Winter",
    "samaa":          "Summer",
    "ootamu":         "Autumn",
    "roozu":          "Rose",
    "baraado":        "Ballad",
    "paateii":        "Party",

    # --- General music / common loanwords in song titles ---
    "myuujikku":      "Music",
    "sooru":          "Soul",
    "haamonii":       "Harmony",
    "merodii":        "Melody",
    "rizumu":         "Rhythm",
    "teema":          "Theme",
    "konsaato":       "Concert",
    "oopera":         "Opera",
    "suonata":        "Sonata",
    "fanfare":        "Fanfare",
    "masutaa":        "Master",
    "supaaku":        "Spark",
    "ruuzu":          "Loose",
    "rein":           "Rain",
    "meigasu":        "Magus",
    "buruu":          "Blue",
    "guriin":         "Green",
    "orenji":         "Orange",
    "raito":          "Light",
    "wairudo":        "Wild",
    "rejendo":        "Legend",
    "fainaru":        "Final",
    "etaanaru":       "Eternal",
    "haato":          "Heart",
    "monsutaa":       "Monster",
    "endoresu":       "Endless",
    "paaku":          "Park",

    # --- Touhou Project: song title vocabulary (katakana loanwords in titles) ---
    "noorejji":       "Knowledge",
    "resurrekushon":  "Resurrection",
    "enjeru":         "Angel",
    "pawaa":          "Power",
    "akusesu":        "Access",
    "rifurekushon":   "Reflection",
    "oouen":          "Owen",
    "oowen":          "Owen",
    "purein'eijia":   "Plain Asia",
    "obu":            "of",
    "jierashii":      "Jealousy",
    "fooru":          "Fall",
    "rasuto":         "Last",
    "rimooto":        "Remote",
    "goosuto":        "Ghost",
    "riido":          "Lead",
    "rijiddo":        "Rigid",
    "paradaisu":      "Paradise",
    "dezaia":         "Desire",
    "doraibu":        "Drive",
    "doriimu":        "Dream",
    "sukoa":          "Score",
    "fearii":         "Fairy",
    "dansu":          "Dance",
    "nokutaan":       "Nocturne",
    "pureryuudo":     "Prelude",
    "fuuga":          "Fugue",

    # ============================================================
    # PC-98 era
    # ============================================================
    "iisutan":          "Eastern",       # テーマ・オブ・イースタンストーリー (th_main)
    "sutoorii":         "Story",         # テーマ・オブ・イースタンストーリー (th_main)
    "airisu":           "Iris",          # アイリス (th01_14)
    "ekisutora":        "Extra",         # エキストララブ (th02_12)
    "rabu":             "Love",          # エキストララブ (th02_12)
    "geemu":            "Game",          # ゲームオーバー (th03_20)
    "oobaa":            "Over",          # ゲームオーバー (th03_20)
    "maesutera":        "Maestra",       # アリスマエステラ (th04_09)
    "purasuchikku":     "Plastic",       # プラスチックマインド (th05_07)
    "maindo":           "Mind",          # プラスチックマインド (th05_07)
    "meipuru":          "Maple",         # メイプルワイズ (th05_08)
    "waizu":            "Wise",          # メイプルワイズ (th05_08)
    "kyuariasu":        "Curious",       # キュアリアス上海古牌 (thmj_01)

    # ============================================================
    # Shuusou Gyoku / Kioh Gyoku spinoffs
    # ============================================================
    "forusu":           "False",         # フォルスストロベリー (sh01_02)
    "sutoroberii":      "Strawberry",    # フォルスストロベリー (sh01_02)
    "purimuroozu":      "Primrose",      # プリムローズシヴァ (sh01_03)
    "shiva":            "Shiva",         # プリムローズシヴァ (sh01_03)
    "dizasutorasu":     "Disastrous",    # ディザストラスジェミニ (sh01_05)
    "jiemini":          "Gemini",        # ディザストラスジェミニ (sh01_05)
    "aamii":            "Army",          # 天空アーミー (sh01_07)
    "supuutoniku":      "Sputnik",       # スプートニク幻夜 (sh01_08)
    "saakasu":          "Circus",        # 機械サーカス (sh01_09, mcd_01_07)
    "revarie":          "Reverie",       # サーカスレヴァリエ (mcd_01_07)
    "kanaberaru":       "Canaveral",     # カナベラルの夢幻少女 (sh01_10)
    "anteiiku":         "Antique",       # アンティークテラー (sh01_12)
    "teraa":            "Terror",        # アンティークテラー (sh01_12)
    "shiruku":          "Silk",          # シルクロードアリス (sh01_16)
    "roodo":            "Road",          # シルクロードアリス (sh01_16)
    "taitoru":          "Title",         # タイトルドメイド (sh01_20)
    "meido":            "Maid",          # タイトルドメイド, メイド幻想, etc.
    "orufe":            "Orpheus",       # オルフェの詩 (sh02_04)
    "orurean":          "Orleans",       # オルレアンの聖騎士 (sh02_06)
    "enigumateiku":     "Enigmatic",     # エニグマティクドール (sh02_10, mcd_01_06)
    "dooru":            "Doll",          # エニグマティクドール (sh02_10, mcd_01_06)
    "riiinkaaneishon":  "Reincarnation", # リーインカーネイション (mcd_01_10)

    # ============================================================
    # Embodiment of Scarlet Devil
    # ============================================================
    "ruuneito":         "Lunate",        # ルーネイトエルフ (th06_04)
    "vuwaru":           "Voile",         # ヴワル魔法図書館 (th06_08) — alt katakana for Voile alongside existing voiru
    "rakuto":           "Locked",        # ラクトガール (th06_09) — official English subtitle is "Locked Girl"  # ⚠ short key
    "gaaru":            "Girl",          # ラクトガール (th06_09)
    "tsuepeshu":        "Tepes",         # ツェペシュの幼き末裔 (th06_12) — alt katakana alongside existing tepesu

    # ============================================================
    # Perfect Cherry Blossom
    # ============================================================
    "kurisutaraizu":    "Crystallize",   # クリスタライズシルバー (th07_03)
    "shirubaa":         "Silver",        # クリスタライズシルバー (th07_03)
    "aruteimetto":      "Ultimate",      # アルティメットトゥルース (th07_12)
    "touruusu":         "Truth",         # アルティメットトゥルース (th07_12)
    "boodaa":           "Border",        # ボーダーオブライフ (th07_14)
    "raifu":            "Life",          # ボーダーオブライフ (th07_14)

    # ============================================================
    # Imperishable Night
    # ============================================================
    "shinderera":       "Cinderella",    # シンデレラケージ (th08_11)
    "keeji":            "Cage",          # シンデレラケージ (th08_11)
    "voyaaju":          "Voyage",        # ヴォヤージュ1969/1970 (th08_13, th08_16)
    "ekusutendo":       "Extend",        # エクステンドアッシュ (th08_17)
    "asshu":            "Ash",           # エクステンドアッシュ (th08_17)

    # ============================================================
    # Phantasmagoria of Flower View / Shoot the Bullet
    # ============================================================
    "orientaru":        "Oriental",      # オリエンタルダークフライト (th09_03)
    "daaku":            "Dark",          # オリエンタルダークフライト (th09_03), 運命のダークサイド (th10_05)
    "furaito":          "Flight",        # オリエンタルダークフライト (th09_03)
    "furawaringu":      "Flowering",     # フラワリングナイト (th09_04)
    "naito":            "Night",         # フラワリングナイト (th09_04), メイガスナイト (th128_08)
    "poizun":           "Poison",        # ポイズンボディ (th09_12)
    "bodi":             "Body",          # ポイズンボディ (th09_12)
    "retorosupekuteibu": "Retrospective", # レトロスペクティブ京都 (th095_05)

    # ============================================================
    # Mountain of Faith
    # ============================================================
    "daakusaido":       "Dark Side",     # 運命のダークサイド (th10_05) — compound; also covered by daaku + saido
    "saido":            "Side",          # ダークサイド (th10_05)  # ⚠ short key
    "neiteibu":         "Native",        # ネイティブフェイス (th10_15)
    "neeteibu":         "Native",        # ネイティブフェイス (th10_15)
    "feisu":            "Faith",          # ネイティブフェイス (th10_15)
    "pureiyaazu":       "Player's",      # プレイヤーズスコア (th10_18)

    # ============================================================
    # Alcostg / Fairy Wars era
    # ============================================================
    "remuria":          "Lemuria",       # レムリア (alcostg_06)
    "miruku":           "Milk",          # サニーミルク (mcd_fairy02_01)
    "saniimiruku":      "Sunny Milk",    # サニーミルク — compound form

    # ============================================================
    # Subterranean Animism
    # ============================================================
    "haatoferuto":      "Heartfelt",     # ハートフェルトファンシー (th11_08)
    "fanshii":          "Fancy",         # ハートフェルトファンシー (th11_08)
    "rarabai":          "Lullaby",       # 廃獄ララバイ (th11_10)
    "mantoru":          "Mantle",        # 業火マントル (th11_12)
    "harutoman":        "Hartmann",      # ハルトマンの妖怪少女 (th11_15), mcd_scoow05_02
    "enerugii":         "Energy",        # エネルギー黎明 (th11_17)

    # ============================================================
    # Undefined Fantastic Object
    # ============================================================
    "sukai":            "Sky",           # スカイルーイン (th12_06)
    "ruuin":            "Ruin",          # スカイルーイン (th12_06)
    "kyaputen":         "Captain",       # キャプテン・ムラサ (th12_09)
    "esoteria":         "Esoteria",      # エソテリア (th12_10) — coined name
    "yuufoo":           "UFO",           # ユーフォーロマンス (th12_14)
    "romansu":          "Romance",       # ユーフォーロマンス (th12_14)
    "eirian":           "Alien",         # 平安のエイリアン (th12_15)
    "announ":           "Unknown",       # アンノウンＸ (th123_10, th145_ps4_06)

    # ============================================================
    # Ten Desires / Hopeless Masquerade / Urban Legend in Limbo
    # ============================================================
    "nyuusu":           "News",          # ニュースハウンド (th125_01)
    "haundo":           "Hound",         # ニュースハウンド (th125_01)
    "modan":            "Modern",        # 妖怪モダンコロニー (th125_03)
    "koronii":          "Colony",        # 妖怪モダンコロニー (th125_03)
    "nemeshisu":        "Nemesis",       # ネメシスの要塞 (th125_04)
    "anrokku":          "Unlock",        # はたてアンロック (th125_07)
    "peshimizumu":      "Pessimism",     # ペシミズム (th135_01, th135_13)
    "emooshon":         "Emotion",       # 亡失のエモーション (th135_12)
    "waado":            "Word",          # ラストワード発動 (th135_34)
    "middonaito":       "Midnight",      # ミッドナイトスペルカード (th143_03)
    "superu":           "Spell",         # スペルカード (th143_03, mcd_ssib_02)
    "kaado":            "Card",          # スペルカード (th143_03, mcd_ssib_02)
    "superukaado":      "Spell Card",    # スペルカード — compound form
    "romanchikku":      "Romantic",      # ロマンチック逃旅行 (th143_04)
    "shoudaun":         "Showdown",      # ショウダウン (th145_06)
    "okaruto":          "Occult",        # オカルトアラカルト (th145_04)
    "arakaruto":        "a la carte",    # オカルトアラカルト (th145_04)
    "atorakuto":        "Attract",       # オカルトアトラクト (th145_ps4_04)
    "infureimu":        "Inflame",       # インフレイム (th145_12, th145_ps4_02)
    "batorufiirudo":    "Battlefield",   # バトルフィールド (th145_14)
    "fookuroa":         "Folklore",      # フォークロア (th145_15, th145_ps4_05, th155_32)
    "okaruteizumu":     "Occultism",     # ラストオカルティズム (th145_16)

    # ============================================================
    # Double Dealing Character
    # ============================================================
    "misuto":           "Mist",          # ミストレイク (th14_02)
    "reiku":            "Lake",          # ミストレイク (th14_02)
    "maameido":         "Mermaid",       # マーメイド (th14_03)
    "deyurahan":        "Dullahan",      # デュラハン (th14_05)
    "ueaurufu":         "Werewolf",      # ウェアウルフ (th14_07)
    "majikaru":         "Magical",       # マジカルストーム (th14_08)
    "sutoomu":          "Storm",         # マジカルストーム (th14_08)
    "ribaasu":          "Reverse",       # リバースイデオロギー (th14_11)
    "ideorogii":        "Ideology",      # リバースイデオロギー (th14_11)
    "biito":            "Beat",          # 始原のビート (th14_15)

    # ============================================================
    # Legacy of Lunatic Kingdom
    # ============================================================
    "panpukin":         "Pumpkin",       # パンプキン (th15_05)
    "hoiiru":           "Wheel",         # ホイールオブフォーチュン (th15_09)
    "foochun":          "Fortune",       # ホイールオブフォーチュン (th15_09)
    "boyaaju":          "Voyage",        # ボヤージュ (th15_10) — different katakana from ヴォヤージュ (voyaaju)
    "piero":            "Pierrot",       # ピエロ (th15_11)
    "pyua":             "Pure",          # ピュアヒューリーズ (th15_13)
    "hyuuriizu":        "Furies",        # ピュアヒューリーズ (th15_13)
    "pyuahyuuriizu":    "Pure Furies",
    "pandemonikku":     "Pandemoniac",   # パンデモニックプラネット (th15_15)
    "puranetto":        "Planet",        # パンデモニックプラネット (th15_15)

    # ============================================================
    # Hidden Star in Four Seasons
    # ============================================================
    "enkauntaa":        "Encounter",     # エンカウンター (th16_05)
    "howaito":          "White",         # ホワイトトラベラー (th16_08)
    "toraberaa":        "Traveler",      # ホワイトトラベラー (th16_08)
    "kureijii":         "Crazy",         # クレイジーバックダンサーズ (th16_11)
    "bakku":            "Back",          # バックダンサーズ / バックドア (th16_11, th16_12)
    "dansaazu":         "Dancers",       # バックダンサーズ (th16_11)
    "intou":            "Into",          # イントゥ・バックドア (th16_12)
    "fooshiizunzu":     "Four Seasons",  # フォーシーズンズ (th16_13) — compound form
    "shiizunzu":        "Seasons",       # フォーシーズンズ (th16_13) — component form if MeCab splits
    "karaa":            "Color",         # フォーカラーラビリンス (th20_08)

    # ============================================================
    # Antinomy of Common Flowers / Violet Detector
    # ============================================================
    "masshuruumu":      "Mushroom",      # マッシュルーム・ワルツ (th155_20)
    "warutsu":          "Waltz",         # マッシュルーム・ワルツ (th155_20)
    "reddo":            "Red",           # レッドソウル (th155_29)
    "souru":            "Soul",          # レッドソウル (th155_29) — ソウル; distinct from ソール (sooru already in dict)
    "suriipu":          "Sleep",         # スリープシープ・パレード (th155_34)
    "shiipu":           "Sheep",         # スリープシープ・パレード (th155_34)
    "pareedo":          "Parade",        # スリープシープ・パレード (th155_34)
    "egoisuto":         "Egoist",        # エゴイスト (th155_37)
    "ruushiddo":        "Lucid",         # ルーシッドドリーマー (th165_02)
    "doriimaa":         "Dreamer",       # ルーシッドドリーマー / ルナティックドリーマー (th165_02, th165_03)
    "runateikku":       "Lunatic",       # ルナティックドリーマー (th165_03)
    "naitomea":         "Nightmare",     # ナイトメアダイアリー (th165_04)
    "daiarii":          "Diary",         # ナイトメアダイアリー (th165_04)

    # ============================================================
    # Wily Beast and Weakest Creature
    # ============================================================
    "jierii":           "Jelly",         # ジェリーストーン (th17_03)
    "sutoon":           "Stone",         # ジェリーストーン (th17_03)
    "rosuto":           "Lost",          # ロストリバー (th17_04)
    "ribaa":            "River",         # ロストリバー (th17_04)
    "serafikku":        "Seraphic",      # セラフィックチキン (th17_07)
    "chikin":           "Chicken",       # セラフィックチキン (th17_07)
    "anrokeiteddo":     "Unlocated",     # アンロケイテッドヘル (th17_08)
    "heru":             "Hell",          # アンロケイテッドヘル (th17_08)
    "tootasu":          "Tortoise",      # トータスドラゴン (th17_09)
    "doragon":          "Dragon",        # トータスドラゴン (th17_09), スモーキングドラゴン (th18_07)
    "biisuto":          "Beast",         # ビーストメトロポリス (th17_10)
    "metoroporisu":     "Metropolis",    # ビーストメトロポリス (th17_10)
    "seramikkusu":      "Ceramics",      # セラミックス (th17_11)
    "erekutorikku":     "Electric",      # エレクトリックヘリテージ (th17_12)
    "heriteeji":        "Heritage",      # エレクトリックヘリテージ (th17_12)
    "pegasasu":         "Pegasus",       # ペガサス (th17_15)

    # ============================================================
    # Unconnected Marketeers
    # ============================================================
    "kitoun":           "Kitten",        # 大吉キトゥン (th18_03)
    "bandettorii":      "Banditry",      # バンデットリィテクノロジー (th18_05)
    "tekunorojii":      "Technology",    # バンデットリィテクノロジー (th18_05)
    "paapechuaru":      "Perpetual",     # パーペチュアルスノー (th18_06)
    "sunoo":            "Snow",          # パーペチュアルスノー (th18_06)
    "sumookingu":       "Smoking",       # スモーキングドラゴン (th18_07)
    "reinboo":          "Rainbow",       # ルナレインボー (th18_12)
    "purinsesu":        "Princess",      # プリンセス (th18_15)

    # ============================================================
    # 100th Black Market / UDoALG / Unfinished Dream of All Living Ghost
    # ============================================================
    "korekutaa":        "Collector",     # コレクター (th185_01)
    "baretto":          "Bullet",        # バレットフィリア (th185_05)
    "firia":            "Philia",        # バレットフィリア (th185_05)
    "burakku":          "Black",         # ブラックマーケット (th185_06)
    "maaketto":         "Market",        # ブラックマーケット (th185_06)
    "sukuranburu":      "Scramble",      # スクランブル (th19_03)
    "tainii":           "Tiny",          # タイニーシャングリラ (th19_05)
    "shangurira":       "Shangri-La",    # タイニーシャングリラ (th19_05)
    "chupakabura":      "Chupacabra",    # チュパカブラ (th19_07)
    "seikuriddo":       "Sacred",        # セイクリッドフォレスト (th20_04)
    "foresuto":         "Forest",        # セイクリッドフォレスト (th20_04)
    "puresute":         "Prester",       # プレステ・ジョアン (th20_06) — Prester John
    "joan":             "John",          # プレステ・ジョアン (th20_06) — Portuguese João
    "reminisensu":      "Reminiscence",  # レミニセンス (th20_09)
    "piramiddo":        "Pyramid",       # ピラミッド (th20_12)
    "fantasuteikku":    "Fantastic",     # ファンタスティックドリフト (th20_14)
    "dorifuto":         "Drift",         # ファンタスティックドリフト (th20_14)
    "harushineeshon":   "Hallucination", # ハルシネーション (th20_15)

    # ============================================================
    # MCD / Doujin albums
    # ============================================================
    "merii":            "Merry",         # 魔術師メリー (mcd_02_06)
    "minittsu":         "Minutes",       # 53ミニッツの青い海 (mcd_04_02)
    "tsuaa":            "Tour",          # 月面ツアーへようこそ (mcd_05_01)
    "gurinijji":        "Greenwich",     # 天空のグリニッジ (mcd_05_02)
    "kafeterasu":       "Cafe Terrace",  # 衛星カフェテラス (mcd_05_06)
    "japaniizu":        "Japanese",      # ジャパニーズサーガ (mcd_pmiss_01)
    "saaga":            "Saga",          # ジャパニーズサーガ (mcd_pmiss_01)
    "ruchiru":          "Rutile",        # サニールチルフレクション (mcd_fairy01_01)
    "furekushon":       "Flection",      # サニールチルフレクション (mcd_fairy01_01)
    "rifureen":         "Refrain",       # リフレーン (mcd_fairy03_01)
    "toroya":           "Trojan",        # トロヤ群の密林 (mcd_06_02) — Trojan asteroid group
    "sanatoriumu":      "Sanatorium",    # 緑のサナトリウム (mcd_07_01)
    "agaruta":          "Agartha",       # アガルタの風 (mcd_07_05)
    "obujiekuto":       "Object",        # イザナギオブジェクト (mcd_07_06)
    "shuredingaa":      "Schrodinger",   # シュレディンガーの化猫 (mcd_08_06)
    "oorudo":           "Old",           # バー・オールドアダム (mcd_09_01)
    "adamu":            "Adam",          # バー・オールドアダム (mcd_09_01)
    "autosaidaa":       "Outsider",      # アウトサイダーカクテル (mcd_09_04)
    "kakuteru":         "Cocktail",      # アウトサイダーカクテル (mcd_09_04)
    "biburofiria":      "Bibliophilia",  # ビブロフィリア (mcd_fs_01)
    "roketto":          "Rocket",        # 明星ロケット (mcd_scoow06_01)
    "saafesu":          "Surface",       # 無生命サーフェス (mcd_scoow04_02)
    "teinkaa":          "Tinker",        # ティンカーベル (mcd_10_02)
    "beru":             "Bell",          # ティンカーベル (mcd_10_02)
    "ootomaata":        "Automata",
    "kuya":             "Cure",
    "fantajii":         "Fantasy",

    # ============================================================
    # 凋叶棕 逆 (sakasa) — C94
    # ============================================================
    "noomoa":           "No More",         # ノーモア (逆 track 2)
    "enimoa":           "Anymore",         # エニモア (逆 track 2)
    "moaamoa":          "More More",       # モアーモア (逆 track 2)
    "hekusentantsu":    "Hexentanz",       # ヘクセン・タンツ (逆 track 3) — German for "witches' dance"

    # ============================================================
    # 凋叶棕 廻 (meguri) — C79
    # ============================================================
    "kareidosukoopu":   "Kaleidoscope",    # カレイドスコープ (廻 track 3)
    "fiirudo":          "Field",           # フィールド (廻 track 6) — スノーフィールド
    "ritaanii":         "Returnee",        # リターニー (廻 track 10) — English loanword
    "himegotokurabu":   "Himegoto Club",   # ヒメゴトクラブ (廻 track EX) — compound form
    "kurabu":           "Club",            # クラブ — general loanword

    # ============================================================
    # 凋叶棕 憩 (ikoi) — 例大祭8
    # ============================================================
    "shiikaa":          "Seeker",          # シーカー (憩 track 1) — スターシーカー
    "udden":            "Wooden",          # ウッデン (憩 track 2)
    "shuuzu":           "Shoes",           # シューズ (憩 track 2)
    "wizu":             "With",            # ウィズ (憩 track 2)
    "ritoru":           "Little",          # リトル (憩 track 2)
    "eregansu":         "Elegance",        # エレガンス (憩 track 2)
    "enshento":         "Ancient",         # エンシェント (憩 track 3)
    "kooringu":         "Calling",         # コーリング (憩 track 3)
    "sukerutso":        "Scherzo",         # スケルツォ (憩 track 4) — musical term

    # ============================================================
    # 凋叶棕 遙 (haruka) — C80
    # ============================================================
    "rutuuru":          "Retour",          # ルトゥール (遙 track 1) — French for "return"
    "shinfonii":        "Symphony",        # シンフォニー (遙 track 1)
    "yugudorashiru":    "Yggdrasil",       # ユグドラシル (遙 track 2) — Norse mythology
    "bodii":            "Body",            # ボディー (遙 track 4) — UniDic long vowel alias
    "kooru":            "Call",            # コール (遙 track 5)

    # ============================================================
    # 凋叶棕 宴 (utage) — C77
    # ============================================================
    "shiriaru":         "Serial",          # シリアル (宴 track 8)
    "kiraa":            "Killer",          # キラー (宴 track 8)

    # ============================================================
    # 凋叶棕 謡 (utai) — C78
    # ============================================================
    "yatagarasukaidaibaa": "Yatagarasu Skydiver",  # ヤタガラスカイダイバー (謡 track 3)
    "aamuchea":         "Armchair",        # アームチェア (謡 track 4)
    "ditekutibu":       "Detective",       # ディテクティブ (謡 track 4)

    # ============================================================
    # 凋叶棕 綴 (tsuduri) — C81
    # ============================================================
    "doa":              "Door",            # ドア (綴 track 1)
    "nokkaa":           "Knocker",         # ノッカー (綴 track 1)
    "honnotabibito":    "Honno Tabibito",  # ホンノタビビト (綴 track 4) — compound form
    "parareru":         "Parallel",        # パラレル (綴 track 6)
    "maddo":            "Mad",             # マッド (綴 track 9)
    "paatii":           "Party",           # パーティー (綴 track 9) — UniDic reading alias
    "wisshu":           "Wish",            # ウィッシュ (綴 track 10)
    "kuroosu":          "Cross",           # クロース (綴 track 10) — long vowel variant
    "kurosu":           "Cross",           # クロス — standard variant
    "feedo":            "Fade",            # フェード (綴 track 10)
    "kuroosufeedo":     "Crossfade",       # クロースフェード — multi-token compound
    "kurosufeedo":      "Crossfade",       # クロスフェード — alt compound
    "ebaa":             "Ever",            # エバー (綴 track 12)
    "eba":              "Ever",            # エバ — short reading variant
    "wandaraa":         "Wanderer",        # ワンダラー (綴 track 12)

    # ============================================================
    # 喩 (tatoe) — C88
    # ============================================================
    "taido":            "Tied",         # タイド (T07) — MeCab splits as ta+ido
    "korapushon":       "Corruption",   # コラプション (T07)
    "taidokorapushon":  "Tied Corruption",  # combined key (T07)
    "waigeruto":        "Wiegelt",      # ワイゲルト — German proper name (T08)
    "redii":            "Lady",         # レディ (T09)
    "paapuru":          "Purple",       # パープル (T09)
    "shadoo":           "Shadow",       # シャドウ (T09)
    "haroo":            "Hello",        # ハロー (T13)
    "furendo":          "Friend",       # フレンド (T13)

    # ============================================================
    # 掲 (kakage) — 例大祭13
    # ============================================================
    "foobidun":         "Forbidden",            # フォービドゥン (T02)
    "fosshiraizudo":    "Fossilized",           # フォッシライズド (T04)
    "gyarakushii":      "Galaxy",               # ギャラクシー (T04)
    "suiito":           "Sweet",                # スイート (T05)
    "kurouraa":         "Crawler",              # クロウラー (T08)
    "resutoresu":       "Restless",             # レストレス (T11)
    "konfineeshon":     "Confinement",          # コンフィネーション (T11)

    # ============================================================
    # 誘 (izanai) — C83
    # ============================================================
    "faindaa":          "Finder",       # ファインダァ (誘T04)

    # ============================================================
    # 徒 (itazura) — 例大祭10
    # ============================================================
    "jenereeshonzu":    "Generations",      # ジェネレーションズ (T02)
    "sutaageizaa":      "Stargazer",        # スターゲイザー (T06)

    # ============================================================
    # 随 (manima) — 例大祭14
    # ============================================================
    "suupaasutaa":      "Superstar",        # スーパースター (T09)
    "kometto":          "Comet",            # コメット (T09)
    "teeru":            "Tail",             # テイル (T09)
    "gurasuhoppaazu":   "Grasshoppers",     # グラスホッパーズ (T10)
    "mochiifu":         "Motif",            # モチーフ (T11)

    # ============================================================
    # △ (tetra) — C99
    # ============================================================
    "messeeji":         "Message",      # メッセージ (T01) — note double-s/long-e phonetics
    "kurasumeeto":      "Classmate",    # クラスメイト (T04)
    "goosutorii":       "Ghostly",      # ゴーストリー (T09) — MeCab splits as goosuto+rii
    # ============================================================
    # Crescendo Planet — C76
    # ============================================================
    "kareidosukuupu":   "Kaleido Scoop",   # カレイドスクープ (track 3)
    "kareido":          "Kaleido",          # カレイド (individual token)
    "sukuupu":          "Scoop",            # スクープ (individual token)
    "byuuteifuru":      "Beautiful",        # ビューティフル (track 4)

    # ============================================================
    # Starry Presto — C77
    # ============================================================
    "shiikuretto":      "Secret",           # シークレット (track 7)
    "shisutaa":         "Sister",           # シスター (track 7)
    "konpurekkusu":     "Complex",          # コンプレックス (track 7)

    # ============================================================
    # Heartcore Forte — 例大祭7
    # ============================================================
    "kuesuto":          "Quest",            # クエスト (track 3)
    "purominensu":      "Prominence",       # プロミネンス (track 6)

    # ============================================================
    # Ultimate Synthesis — C78
    # ============================================================
    "saibaneteikku":    "Cybernetics",      # サイバネティクス (track 9)

    # ============================================================
    # 犬猫的電子座曲 — C91
    # ============================================================
    "garee":            "Galley",       # ガレー (track 4) — short key; low collision risk
                                        # since ガレー rarely appears in other contexts

    # ============================================================
    # ブチアゲ♂トウホウ — 例大祭14
    # ============================================================
    "teurugisuto":      "Theurgist",    # テウルギスト (track 2)
    "biiru":            "Beer",         # ビール (track 16) — short key; high frequency word,
                                        # check for any track where ビール should stay phonetic
    "revarrie":         "Reverie",      # レヴァリエ (track 18) — verify exact plugin key;
                                        # ヴァ = "va" in some plugin tables, "ba" in others
    "parasoru":         "Parasol",      # パラソル (track 19)

    # ============================================================
    # Official-theme coverage audit
    # ============================================================
    # UniDic sometimes emits a different kana reading from the one used by
    # the existing entry, or keeps a complete English-derived title as one
    # token. These aliases and compounds keep the established English
    # spellings without changing the general kanji-reading fallback.

    # Touhou spelling/reading aliases
    "sanii":           "Sunny",        # サニー (mcd_fairy01_01, mcd_fairy02_01)
    "jerashii":        "Jealousy",     # ジェラシー (th11_04)
    "jerii":           "Jelly",        # ジェリー (th17_03)
    "reitenshii":      "Latency",      # レイテンシー (mcd_08_01)
    "retorosupekutibu": "Retrospective", # レトロスペクティブ (th095_05)
    "fantasutikku":    "Fantastic",    # ファンタスティック (th20_14)
    "antiiku":         "Antique",      # アンティーク (Seihou)
    "arutimetto":      "Ultimate",     # アルティメット (th07_12)
    "turuusu":         "Truth",        # トゥルース (th07_12)
    "enigumatiku":     "Enigmatic",    # エニグマティク (Seihou)
    "okarutizumu":     "Occultism",    # オカルティズム (th145_16)
    "obujekuto":       "Object",      # オブジェクト (mcd_07_06)
    "neitibu":         "Native",      # ネイティブ (th10_15)
    "dyurahan":        "Dullahan",    # デュラハン (th14_05)
    "weaurufu":        "Werewolf",    # ウェアウルフ (th14_07)
    "eerihhi":         "Erich",       # エーリッヒ (Seihou)
    "ooen":            "Owen",        # オーエン (th06_15)
    "baajon":          "Version",     # バージョン (unused/century's-end versions)
    "foo":             "Four",        # フォー (th16_13, th20_08)
    "foorin":          "Falling",     # フォーリン (Len'en)
    "shiirudo":        "Shield",      # シールド (Seihou)
    "shindoroomu":     "Syndrome",    # シンドローム (Len'en)
    "terasu":          "Terrace",     # テラス (mcd_05_06)
    "kafe":            "Cafe",        # カフェ (Len'en)
    "waapu":           "Warp",        # ワープ (Seihou)
    "geeto":           "Gate",        # ゲート (Seihou)
    "waarudo":         "World",       # ワールド (Len'en)
    "mataara":         "Matara",      # マターラ (th16_17)
    "fureimu":         "Flame",       # フレイム (th145_12)
    "tiaoietson":      "Diao Ye Zong", # ティアオイエツォン (th07_02)
    "yuanshen":        "Yuanxian",    # ユアンシェン (th13_05)
    "tsepeshu":        "Tepes",       # ツェペシュ (th06_12)
    "tinkaa":          "Tinker",      # ティンカー (mcd_10_02)
    "kitun":           "Kitten",      # キトゥン (th18_03; MeCab splits キ + トゥン)
    "booru":           "Ball",        # ボール (th19_01)
    "puranku":         "Planck",      # プランク (mcd_08_01)
    "hiiroo":          "Hero",        # ヒーロー (Len'en)
    "fukku":           "Hook",        # フック (Len'en)
    "on":              "On",          # オン (Len'en)
    "demo":             "Demo",        # デモ (Seihou)
    "neo":              "Neo",         # ネオ (th145_12)
    "wandaarando":      "Wonderland",  # わんだーらんど (Len'en)
    "radikaru":         "Radical",     # ラディカル (Len'en)
    "runatikku":        "Lunatic",     # ルナティック (th165_03)

    # Touhou title compounds that UniDic keeps as one token
    "arisumaesutera":   "Alice Maestra",       # アリスマエステラ (th04_09)
    "arutimettoturuusu": "Ultimate Truth",    # アルティメットトゥルース (th07_12)
    "ekisutorarabu":    "Extra Love",          # エキストララブ (th02_12)
    "enigumatikudooru": "Enigmatic Doll",      # エニグマティクドール (Seihou)
    "saakasurevarie":   "Circus Reverie",      # サーカスレヴァリエ (mcd_01_07)
    "sukairuuin":       "Sky Ruin",            # スカイルーイン (th12_06)
    "sutaaboudoriimu":  "Starbow Dream",       # スターボウドリーム (mcd_04_01)
    "furawaringunaito": "Flowering Night",     # フラワリングナイト (th09_04)
    "pandemonikkupuranetto": "Pandemonic Planet", # パンデモニックプラネット (th15_15)
    "ruushiddodoriimaa": "Lucid Dreamer",       # ルーシッドドリーマー (th165_02)
    "ruuneitoerufu":   "Lunate Elf",           # ルーネイトエルフ (th06_04)
    "serafikkuchikin": "Seraphic Chicken",     # セラフィックチキン (th17_07)
    "anrokeiteddoheru": "Unlocated Hell",      # アンロケイテッドヘル (th17_08)
    "bandettoriitekunorojii": "Banditry Technology", # バンデットリィテクノロジー (th18_05)
    "meipuruwaizu":    "Maple Wise",           # メイプルワイズ (th05_08)
    "denderaya":        "Dendera",              # デンデラ野 (mcd_04_01)
    "monoai":           "Mono Eye",             # モノアイ (Len'en)
    "baaoorudoadamu":   '"Old Adam" Bar',       # バー・オールドアダム (mcd_09_01)

    # Len'en / Seihou title vocabulary
    "anazaa":           "Another",       # アナザー (Len'en)
    "ea":               "Air",           # エア・マスター (Len'en)
    "ekizochikku":      "Exotic",        # エキゾチック (Len'en)
    "endo":             "End",           # エンド (Len'en)
    "enpaia":           "Empire",        # エンパイア (Len'en)
    "enperaa":          "Emperor",       # エンペラー (Len'en)
    "eejento":          "Agent",         # エージェント (Len'en)
    "oobaahiito":       "Overheat",      # オーバーヒート (Len'en)
    "oobaafuroo":       "Overflow",      # オーバーフロー (Len'en)
    "oobaahooru":       "Overhaul",      # オーバーホール (Len'en)
    "kiringu":          "Killing",       # キリング (Len'en)
    "superioru":        "Superior",      # スペリオル (Len'en)
    "kiipu":            "Keep",          # キープ (Len'en)
    "hisutorii":        "History",       # ヒストリー (Len'en)
    "suragu":           "Slug",          # スラグ (Len'en)
    "daburu":           "Double",        # ダブル (Len'en)
    "kiipaa":           "Keeper",        # キーパー (Len'en)
    "chairudo":         "Child",         # チャイルド (Len'en)
    "nimonikku":        "Mnemonic",      # ニモニック (Len'en)
    "meranin":          "Melanin",       # メラニン (Len'en)
    "manee":            "Money",         # マネー (Len'en)
    "birudaa":          "Builder",       # ビルダー (Len'en)
    "daun":             "Down",          # ダウン (Len'en)
    "fuuru":            "Fool",          # フール (Len'en)
    "akuto":            "Act",           # アクト (Len'en)
    "za":               "the",           # ザ (Len'en)
    "kosumosu":         "Cosmos",        # コスモス (Len'en)
    "mikuro":           "Micro",         # ミクロ (Len'en)
    "geitsu":           "Gates",         # ゲイツ (Seihou)
    "getto":            "Get",           # ゲット (Len'en)
    "afutaa":           "After",         # アフター (Len'en)
    "kiro":             "Kilo",          # キロ (th15_10)

    # Whole-token and multi-token Len'en / Seihou compounds
    "dizasutorasujemini": "Disastrous Gemini",  # ディザストラスジェミニ
    "purimuroozushiva": "Primrose Shiver",      # プリムローズシヴァ
    "haaseruvusu":      "Herselves",            # ハーセルヴス
    "haaseruvuzu":      "Herselves",            # ハーセルヴズ
    "nekuromasutaa":    "Necromaster",          # ネクロマスター
    "suupaahaniiwa":    "Super Haniwa",         # スーパーハニーワ
    "rosutojakkupotto": "Lost Jackpot",        # ロストジャックポット
    "purizumikkuakuseru": "Prismic Accelerator", # プリズミックアクセル
    "purizumikkudoraibu": "Prismic Drive",      # プリズミックドライブ
    "diipuweivaa":      "Deep Waiver",           # ディープウェイヴァー
    "shirukuroodoarisu": "Silk Road Alice",     # シルクロードアリス
    "taitorudomeido":   "Titled Maid",          # タイトルドメイド
    "intu・bakkudoa":   "Into Backdoor",        # イントゥ・バックドア
    "indisuwaarudo":    "In This World",        # インディスワールド
    "meranininburakku": "Melanin in Black",     # メラニンインブラック
    "meidoinburakku":   "Made in Black",        # メイドインブラック
    "afutaaooru":       "After All",            # アフターオール
    "endoobuhisutorii": "End of History",       # エンドオブヒストリー
    "kiipuzahisutorii": "Keep the History",     # キープザヒストリー
    "mukuromansaa":     "Cadaveromancer",        # ムクロマンサー
    "mikurokosumosu":   "Microcosm",             # ミクロコスモス
    "ekusutorakushon":  "Extraction",            # エクストラクション
    "egoerisu":         "Ego Eris",              # エゴエリス
    "akutozafuuru":     "Act the Fool",          # アクト・ザ・フール
    "eamasutaa":        "Air Master",            # エア・マスター
    "gettoradiigou":    "Get Ready... Go!",      # ゲットレディー号
    "rettsuendogou":    "Let's 'n Go",           # レッツエンド号
    "tainiishangurira": "Tiny Shangri-La",      # タイニーシャングリラ
    "ruumuzahisutorii": "Room the History",      # ルームザヒストリー
    "torioido・toukeatto": "Trioid Toykeat",     # トリオイド・トウケアット
}

_TITLE_OVERRIDES: dict[str, str] = {
    # Official Touhou game names.  These are the conventional title
    # readings, rather than whatever general-purpose MeCab happens to
    # choose for the same kanji in ordinary prose.  The phrase table below
    # mirrors these entries for occurrences inside 東方-prefixed titles.
    "靈異伝": "Reiiden",
    "封魔録": "Fuumaroku",
    "夢時空": "Yumejikuu",
    "幻想郷": "Gensoukyou",
    "怪綺談": "Kaikidan",
    "紅魔郷": "Koumakyou",
    "妖々夢": "Youyoumu",
    "萃夢想": "Suimusou",
    "永夜抄": "Eiyashou",
    "花映塚": "Kaeidzuka",
    "文花帖": "Bunkachou",
    "風神録": "Fuujinroku",
    "緋想天": "Hisouten",
    "地霊殿": "Chireiden",
    "星蓮船": "Seirensen",
    "非想天則": "Hisoutensoku",
    "ダブルスポイラー": "Double Spoiler",
    "妖精大戦争": "Yousei Daisensou",
    "神霊廟": "Shinreibyou",
    "心綺楼": "Shinkirou",
    "輝針城": "Kishinjou",
    "深秘録": "Shinpiroku",
    "弾幕アマノジャク": "Danmaku Amanojaku",
    "紺珠伝": "Kanjuden",
    "憑依華": "Hyouibana",
    "天空璋": "Tenkuushou",
    "秘封ナイトメアダイアリー": "Hifuu Nightmare Diary",
    "鬼形獣": "Kikeijuu",
    "剛欲異聞": "Gouyoku Ibun",
    "虹龍洞": "Kouryuudou",
    "バレットフィリア達の闇市場": "Bulletphilia-tachi no Yami-Ichiba",
    "獣王園": "Juuouen",
    "錦上京": "Kinjoukyou",
    # Gold Rush is the one-stage official exhibition game associated with
    # Impossible Spell Card, rather than a numbered installment.
    "ゴールドラッシュ": "Gold Rush",

    # Full 東方-prefixed forms are listed separately because MeCab can give
    # 東方 a context-dependent reading (e.g. ヒガシカタ or トウボウ).
    "東方靈異伝": "Touhou Reiiden",
    "東方封魔録": "Touhou Fuumaroku",
    "東方夢時空": "Touhou Yumejikuu",
    "東方幻想郷": "Touhou Gensoukyou",
    "東方怪綺談": "Touhou Kaikidan",
    "東方紅魔郷": "Touhou Koumakyou",
    "東方妖々夢": "Touhou Youyoumu",
    "東方萃夢想": "Touhou Suimusou",
    "東方永夜抄": "Touhou Eiyashou",
    "東方花映塚": "Touhou Kaeidzuka",
    "東方文花帖": "Touhou Bunkachou",
    "東方風神録": "Touhou Fuujinroku",
    "東方緋想天": "Touhou Hisouten",
    "東方地霊殿": "Touhou Chireiden",
    "東方星蓮船": "Touhou Seirensen",
    "東方非想天則": "Touhou Hisoutensoku",
    "東方神霊廟": "Touhou Shinreibyou",
    "東方心綺楼": "Touhou Shinkirou",
    "東方輝針城": "Touhou Kishinjou",
    "東方深秘録": "Touhou Shinpiroku",
    "東方紺珠伝": "Touhou Kanjuden",
    "東方憑依華": "Touhou Hyouibana",
    "東方天空璋": "Touhou Tenkuushou",
    "東方鬼形獣": "Touhou Kikeijuu",
    "東方剛欲異聞": "Touhou Gouyoku Ibun",
    "東方虹龍洞": "Touhou Kouryuudou",
    "東方獣王園": "Touhou Juuouen",
    "東方錦上京": "Touhou Kinjoukyou",

    # Source-supported readings from the ambiguous-title investigation.
    # Umineko Essence (KNIL-0004):
    # https://07th-expansion.fandom.com/wiki/Umineko_no_Naku_Koro_ni_Episode.1_Original_Soundtrack_Essence
    "煉沙回廊": "Rensa Kairou",
    # Publisher explicitly gives ショウエン セイキツ:
    # https://www.4gamer.net/games/429/G042972/20180809115/
    "燋燄誓契": "Shouen Seikitsu",
    # Known theme bases, including simplified-Chinese spelling aliases.
    # Keep these scoped to titles; a global character conversion would also
    # reinterpret Chinese translations as if they were Japanese originals.
    "少女綺想曲": "Shoujo Kisoukyoku",
    "少女绮想曲": "Shoujo Kisoukyoku",
    "二色蓮花蝶": "Nishiki Rengechou",
    "二色莲花蝶": "Nishiki Rengechou",
    "有頂天変": "Uchoutenpen",
    "有顶天变": "Uchoutenpen",
    "幻想郷の二ッ岩": "Gensokyo no Futatsuiwa",
    "幻想乡の二ッ岩": "Gensokyo no Futatsuiwa",
    # 瑰意琦行 is the dictionary expression かいいきこう:
    # https://yoji.jitenon.jp/yojim/6398
    "鎮座する瑰意琦行": "Chinza Suru Kaiikikou",
    "蓬莱の薬 ~死ぬこと無き者達": "Hourai no Kusuri ~Shinu Koto Naki Monotachi",
    "蓬莱の薬　~死ぬこと无き者达": "Hourai no Kusuri ~Shinu Koto Naki Monotachi",
    # The artist's own track URL supplies the reading Ama hiki:
    # https://soundcloud.com/nesarfmollor/amahiki-springs-arrival-heralded-by-the-thunder-of-lightning
    "雩 - 春の訪れと共に稲妻が鳴り響く":
        "Amahiki - Haru no Otozure to Tomo ni Inazuma ga Narihibiku",
    # 広有射怪鳥事 — archaic Heian proper noun + unconventional readings
    # 蠢々秋月 — 秋月 read with on'yomi rather than the usual kun'yomi
    "ひもろぎ、むらさきにもえ": "Himorogi, Murasaki ni Moe",
    "明日ハレの日、ケの昨日":  "Ashita Hare no Hi, Ke no Kinou",

    # EastNewSound comma titles — MeCab/UniDic frequently chooses literal
    # kanji readings here, while the song titles use coined/proper-name
    # readings.  Keep these as whole-title overrides so the title-specific
    # readings do not affect unrelated Japanese text.
    "逢魔紅月、奉還ノ絶": "Oumakougetsu, Houkan no Zetsu",
    "位念我相、狂波ノ絶": "Inengasou, Kyouha no Zetsu",
    "鬼獣羅漢、業炎ノ絶": "Kijuurakan, Gouka no Zetsu",
    "幻奏幻花、届かずの音色": "Gensou Genka, Todokazu no Neiro",
    "紅煙月下、惨生ノ絶": "Kouen Gekka, Zanshou no Zetsu",
    "酷翼残下、堕空ノ絶": "Shouyoku Zanka, Dakuu no Zetsu",
    "死生信艶、暴謳ノ絶": "Shishou Shin'en, Bouou no Zetsu",
    "死奏燐音、玲瓏ノ終": "Shisou Rinne, Reirou no Tsui",
    "焼痕煉黑、冷艶ノ絶": "Shoukon Rengoku, Reien no Zetsu",
    "纏金鳳花、欲動ノ絶": "Tenkin Bouge, Yokudou no Zetsu",
    "透純幻夢、愛憎ノ絶": "Toujun Genmu, Aizou no Zetsu",
    "秘神瞳碍、七星ノ絶": "Hishindouge, Nanahoshi no Zetsu",
    "風導星歌、黎明ノ景": "Fuudou Seika, Reimei no Kei",
    "幽音絶花、繚乱ノ彩": "Yuune Zekka, Ryouran no Sai",
    "滲色血界、月狂ノ獄": "Nijiiro Kekkai, Gekkyou no Goku",
    # This title's reading is less consistently documented; this is the
    # best available reading used by the catalog research.
    "祟境曲下、彩酸ノ絶": "Suikyoukyokka, Saisan no Zetsu",
    "髑薬遊戯、解魂ノ絶": "Dokuyakuyuugi, Kaikon no Zetsu",
    "緋色月下、狂咲ノ絶": "Hiiro Gekka, Kyoushou no Zetsu",
    "さよなら、夜空": "Sayonara, Yozora",
}

# Reviewed orthographic variants of Japanese title bases from the library
# audit. Convert only a complete, delimited match, never all Chinese text.
# Values deliberately retain Japanese grammar and words: these are spelling
# aliases, not Chinese translations. Unverified readings such as 橤の想い
# stay unresolved until there is evidence for the artist's intended reading.
_TITLE_SPELLING_ALIASES: dict[str, str] = {
    # Source-supported Japanese identities, reviewed 2026-09-09. These
    # exact title spellings are intentional exceptions to the language gate;
    # they do not establish that the same characters in other titles are JP.
    # Umineko Essence (KNIL-0004), same catalog as 煉沙回廊 above.
    "蔷薇": "薔薇",
    "炼沙回廊": "煉沙回廊",
    "牢狱STRIP": "牢獄STRIP",
    # IRON ATTACK!, 宇宙とファンタジー:
    # https://ironattack.theshop.jp/items/5169790
    "浪漫纪行": "浪漫紀行",
    # SOUND HOLIC, DARK SLEEPER:
    # https://shop.akbh.jp/products/2100000044061
    "百花缭乱": "百花繚乱",
    # TAMUSIC, TAM3-0233, track 21:
    # https://www.melonbooks.co.jp/detail/detail.php?product_id=2759939
    "幽灵乐团 · 幽雅に咲かせ、墨染の桜": "幽霊楽団 · 幽雅に咲かせ、墨染の桜",
    # 半裸帝国, VI: spelling verified; the event's intended reading is
    # not documented, so leave pronunciation to the engine rather than
    # asserting an unverified whole-title romaji override.
    # https://booth.pm/en/items/2032140
    "瑠璃色幻想鄉(Live at東方艷騷会Vol.3)": "瑠璃色幻想郷(Live at 東方艶騒会Vol.3)",
    # 揺蕩夢澪標: https://booth.pm/ja/items/3218990
    "大神神话传": "大神神話伝",
    # AramiTama, The Tribe (also in SPECIAL TOHO TECHNO DJ MIX):
    # https://arami.rdy.jp/disc/tribe.html
    "沉泥": "沈泥",
    # 葉月ゆら, ゆらわーるど -Honey Bee-:
    # https://www.suruga-ya.jp/product/detail/186140782
    "轮廻": "輪廻",
    "弦楽四重奏曲第１番ト长调": "弦楽四重奏曲第1番ト長調",
    "オルガン小曲 第６亿番 ハ短调": "オルガン小曲 第6億番 ハ短調",
    "眠り死の月の時计": "眠り死の月の時計",
    "東の国探查": "東の国探査",
    "梦と现の境界": "夢と現の境界",
    "流雲に隱れた幻想鄉": "流雲に隠れた幻想郷",
    "摇蕩う光": "揺蕩う光",
    "ヴワル魔法図书馆": "ヴワル魔法図書館",
    "梦の华": "夢の華",
    "伝說の夢の国": "伝説の夢の国",
    "君の笑颜": "君の笑顔",
    "东方の夜明けより": "東方の夜明けより",
    "闭ざせし云の通い路": "閉ざせし雲の通い路",
    "メイドと血の懐中时计": "メイドと血の懐中時計",
    "目覚めし红き王女": "目覚めし紅き王女",
    "亡き王女の为のセプテット": "亡き王女の為のセプテット",
    "光阴ナイフの如し": "光陰ナイフの如し",
    "永远の巫女": "永遠の巫女",
    "蓬莱の薬　~死ぬこと无き者达": "蓬莱の薬 ~死ぬこと無き者達",
    "れみりゃのある日のティータイム!!~マリサ乱入编~":
        "れみりゃのある日のティータイム!!~マリサ乱入編~",
    "朱蚀マリアージュ": "朱蝕マリアージュ",
    "進擊せよ、小槌振りて": "進撃せよ、小槌振りて",
    "マジ〇チ青森產トマト出荷": "マジ〇チ青森産トマト出荷",
    "幻想乡の夏": "幻想郷の夏",
    "死灵の夜樱": "死霊の夜桜",
    "红楼の雨，上海の泪": "紅楼の雨,上海の泪",
    "末那の呗": "末那の唄",
    "樱花の呗": "桜花の唄",
    "信仰は儚き人间の为に": "信仰は儚き人間の為に",
    "鲜烈の华": "鮮烈の華",
    "世界を变える風": "世界を変える風",
    "废狱の唄": "廃獄の唄",
    "幽灵ちゃんダッシュパンチ": "幽霊ちゃんダッシュパンチ",
    "暧昧な存在": "曖昧な存在",
    "涡ノ霧": "渦ノ霧",
    "夏を飞び越えて": "夏を飛び越えて",
    "蔷薇と弾丸": "薔薇と弾丸",
    "赤い明日、绮想の音": "赤い明日、綺想の音",
    "月背の観测者": "月背の観測者",
    "兄贵の歌声": "兄貴の歌声",
}

# Phrase-level overrides: tuple of MeCab surface strings → Romaji.
# Applied before loanword matching, longest-match-first (up to 4 tokens).
# Use this when MeCab splits a known compound into pieces that loanword
# lookup cannot reassemble (e.g. a coined place name with no UniDic entry).
# Keys are tuples of exact surface forms as MeCab produces them.
# Example:
#   ("幻想", "郷"): "Gensokyo",
_PHRASE_OVERRIDES: dict[tuple, str] = {
    # Official Touhou game names.  Keep these phrase-level forms in sync
    # with the bare-title overrides above so 東方-prefixed and embedded game
    # names use the same conventional readings.
    ("靈異", "伝"): "Reiiden",
    ("封", "魔", "録"): "Fuumaroku",
    ("夢", "時空"): "Yumejikuu",
    ("東方", "幻想", "郷"): "Touhou Gensoukyou",
    ("怪", "綺談"): "Kaikidan",
    ("紅", "魔", "郷"): "Koumakyou",
    ("萃", "夢想"): "Suimusou",
    ("永", "夜", "抄"): "Eiyashou",
    ("花", "映塚"): "Kaeidzuka",
    ("文", "花", "帖"): "Bunkachou",
    ("風神", "録"): "Fuujinroku",
    ("緋想", "天"): "Hisouten",
    ("地霊", "殿"): "Chireiden",
    ("星蓮", "船"): "Seirensen",
    ("非想", "天", "則"): "Hisoutensoku",
    ("ダブル", "スポイラー"): "Double Spoiler",
    ("妖精", "大", "戦争"): "Yousei Daisensou",
    ("神", "霊廟"): "Shinreibyou",
    ("心", "綺", "楼"): "Shinkirou",
    ("輝", "針", "城"): "Kishinjou",
    ("深", "秘録"): "Shinpiroku",
    ("弾幕", "アマノジャク"): "Danmaku Amanojaku",
    ("紺", "珠", "伝"): "Kanjuden",
    ("憑依", "華"): "Hyouibana",
    ("天空", "璋"): "Tenkuushou",
    ("秘", "封", "ナイトメア", "ダイアリー"): "Hifuu Nightmare Diary",
    ("鬼形", "獣"): "Kikeijuu",
    ("剛", "欲", "異聞"): "Gouyoku Ibun",
    ("虹", "龍", "洞"): "Kouryuudou",
    ("バレット", "フィリア", "達", "の", "闇", "市場"):
        "Bulletphilia-tachi no Yami-Ichiba",
    ("獣王", "園"): "Juuouen",
    ("錦", "上京"): "Kinjoukyou",
    ("ゴールド", "ラッシュ"): "Gold Rush",

    ("幻想", "郷"): "Gensokyo",
    ("妖", "々", "夢"): "Youyoumu",
    ("妖", "々", "跋扈"): "Youyou Bakko",
    ("広", "有", "射", "怪鳥", "事"): "Hiroari Kechou wo Iru Koto",
    ("蠢", "々", "秋月"): "Shunshun Shuugetsu",
    ("素", "い", "幡"): "Shiroi Hata",
    ("弦", "奏", "交響", "曲"): "Gensou Koukyoukyoku",
    ("御", "阿礼", "幻想", "艶", "戯", "譚"): "Miare Gensou Engitan",
    ("無", "炎", "舞踊"): "Muenbuyou",
    ("白", "玉", "楼"): "Hakugyokurou",
    ("蓬", "莱"): "Hourai",
    ("命", "蓮", "寺"): "Myourenji",
    ("けー", "ね"): "Keine",
    ("千", "年"): "Sennen",
    ("綺想", "曲"): "Kisoukyoku",
    ("摩天", "楼"): "Matenrou",
    ("神さび", "た"): "Kamisabita",
    ("古", "戦場"): "Kosenjou",

    # 符 compound — MeCab always splits 〇 + 符; several also have wrong on/kun reading.
    # All 符 names in this album use on'yomi.
    ("始", "符"):           "Shifu",        # T01
    ("禁", "符"):           "Kinfu",        # T02
    ("契", "符"):           "Keifu",        # T03 — MeCab reads 契 as kun'yomi "chigiri"
    ("薬", "符"):           "Yakufu",       # T04 — MeCab reads 薬 as kun'yomi "kusuri"
    ("蝕", "符"):           "Shokufu",      # T05
    ("祭", "符"):           "Saifu",        # T06 — MeCab reads 祭 as kun'yomi "matsuri"
    ("核", "符"):           "Kakufu",       # T07
    ("惑", "符"):           "Wakufu",       # T08 (already correct, but add for consistency)
    ("邪", "符"):           "Jafu",         # T09 — MeCab reads 邪 as kun'yomi "yokoshima"
    ("逆", "符"):           "Gyakufu",      # T10
    ("獄", "符"):           "Gokufu",       # T11 — MeCab reads 獄 as kun'yomi "hitoya"

    # T01 subtitle errors
    ("博", "麗"):           "Hakurei",          # proper noun split
    ("決闘", "法"):         "Kettouhou",        # compound law term

    # T03 subtitle
    ("狐", "憑"):           "Kitsunehyou",      # compound noun split

    # Murasa is a proper-name ending; UniDic tags the final サ as a particle.
    ("ムラ", "サ"):         "Murasa",            # キャプテン・ムラサ

    # T10 subtitle — yojijukugo read as all on'yomi
    ("前", "退", "後", "進"):    "Zentaikoushin",    # 前 misread as "mae"
}

# Explicit non-Japanese exceptions to the default-Japanese file-tagging policy.
# Whole parent-directory names, case-insensitive; applies to all descendants.
# These identify reviewed Chinese soundtrack releases, not artist nationality.
_NON_JAPANESE_DIRECTORIES: set[str] = {
    "Mystia's Izakaya",
    "Touhou Mystia's Izakaya OST1",
    "Touhou Mystia's Izakaya OST2",
    "Touhou Mystia's Izakaya OST3",
    "东方光耀夜 ~ Touhou Lost Branch of Legend OST [FLAC]",
}

# Exact titles verified as Chinese during the 2026-09-09 investigation.
# Do not populate this from merely ambiguous shared-Han words.
_NON_JAPANESE_TITLES: set[str] = {
    "我亲爱傀儡",  # Shibayan: published Chinese wording
    "背水一战",  # Avenue Room: published as Bei shui yi zhan
    "好久不见",  # MISTY RAIN: published as Haojiubujian
    "伽蓝雨",  # A-One: Chinese title and lyrics
}


# Chinese titles reviewed against published release information (2026-09-09).
# Keys are adjacent (circle directory, album directory) names; values are
# exact recorded titles, including explicitly reviewed metadata variants.
# Do not skip whole circles or mixed-language albums. Japanese neighbors and
# the same shared-Han title on another release remain eligible.
_NON_JAPANESE_RELEASE_TITLES: dict[tuple[str, str], set[str]] = {
    # https://steamcommunity.com/app/1715460/announcements/
    ('[GAMEPULSE 游戏脉冲]', '2024.12.01 東方冰之勇者記 - 新支持者包'): {
        '兔子时间',
        '雨夜列车',
        '静谧的魔法森林',
        '妖怪大酒馆',
        '不羁奔放~百鬼之王！',
        '至暗时刻',
        '汇集狂热之地',
        '星间轨道',
        '超弦轨道',
        '雾之湖钻头狂',
        '神隐之庭',
        '枫落忆痕',
        '红枫乱舞~觉醒',
        '边境',
        '准备就绪~火力全开！',
        '星河鹭起',
        '不可测集',
        '幻梦颂歌',
        '不可窥探多重梦境',
        '跨越45亿年的羁绊',
    },
    # https://store.steampowered.com/app/3564980/Touhou_Hero_of_Ice_Fairy__Rose_Idol_Soundtrack/
    ('[GAMEPULSE 游戏脉冲]', '2025.05.17 Koi Overdose [东方游剧天14]'): {
        '蔷薇偶像(Live at ©Gensokyo武道馆)',
        '台前妆后',
        '恋语陷阱',
        '妄想感觉操控',
        '对你的爱恋绝非谎言',
        '绝对梦幻玫瑰花瓣',
        '献给你的荆棘之歌',
        '妄想感觉操控(Instrumental)',
        '对你的爱恋绝非谎言(Instrumental)',
        '献给你的荆棘之歌(Instrumental)',
        '对你的爱恋绝非谎言(Studio.Ver)',
        '献给你的荆棘之歌(Studio.Ver)',
    },
    # https://store.steampowered.com/app/4119320/Touhou_Hero_of_Ice_Fairy__Soundtrack2__Ashes_of_The_Moonburn_feat_KujoRyo__Darkxixin/
    ('[GAMEPULSE 游戏脉冲]', '2026.04.26 Touhou Hero of Ice Fairy - Soundtrack 2 - Ashes of The Moonburn'): {
        '不朽不灭，永世业火',
        '永远之歌',
        '缚于永恒的共犯',
        '满月之下~丑时三刻~',
        '须臾之歌~天人的音乐~',
        '兔子帮，出征！',
        '竹取飞去哪？',
        '蓬莱异闻',
        '相杀相依',
        '焚尽不公 (帅气兔子 Remix)',
        '不朽不灭，永世业火 (instrumental)',
        '永远之歌 (instrumental)',
        '缚于永恒的共犯 (Instrumental)',
        '满月之下~丑时二刻~',
        '满月之下~丑时一刻~',
        '须臾之歌~明月的威光~',
        '须臾之歌~永远的庭院~',
    },
    # https://www.101soundboards.com/boards/1139557-cang-yue-xian-ge-touhou-video-game-music
    ('[Giinno Country]', '2022.04.22 [GCCD-01] 苍月弦歌'): {
        '踏雪莲台野',
        '夜萤善光寺',
        '天鸟船神社',
        '静谧的月之里',
        '永夜的追忆',
        '月都旧事，竹取的传说',
    },
    # https://www.dizzylab.net/d/GCCD-02/
    ('[Giinno Country]', '2023.07.23 [GCCD-02] 危楼记事 [广西TH3]'): {
        '危楼回忆录',
        '空与海的记忆',
        '堇色吟游者之梦',
        '逆飞的白昼客星',
        '夜与不可思议',
        '属于二人的现世逃避行',
        '危楼回忆录（inst.）',
    },
    # https://www.dizzylab.net/d/MCG-01/
    ('[MCG音乐组]', '2021.08.07 追忆幻想乡 MineCraft幻想乡九周年纪念CD [魅知幻想博览会 2021 上海场]'): {
        '幻想乡天地缘起',
        '山纹浮响,雨瀑秋间',
        '嫉妒的华尔兹',
        '黄昏中的废弃之都',
        '东京37F',
        '冥界一日风景',
        '闲蝉悬声,云歇浅斟',
        '桃源梦乡',
        '魂牵梦绕之地',
    },
    # https://www.dizzylab.net/d/MCG-01/
    ('[MineCraft幻想乡]', '2021.08.07 追忆幻想乡 [魅知幻想博览会 2021 上海场]'): {
        '幻想乡天地缘起',
        '山纹浮响，雨瀑秋间',
        '嫉妒的华尔兹',
        '黄昏中的废弃之都',
        '东京37F',
        '冥界一日风景',
        '闲蝉悬声，云歇浅斟',
        '桃源梦乡',
        '魂牵梦绕之地',
    },
    # https://www.dizzylab.net/d/SRCP01/
    ('[SORR!COP]', '2023.07.23 [SRCP-01] 馆中舞会邀请函 [广西TH3]'): {
        '满目虚无的红',
        '未见之城',
        '蕾米莉亚好像若无其事的下午',
    },
    # https://www.dizzylab.net/d/SRCP01/
    ('[SORRICOP]', '2023.07.23 [SRCP-01] 馆中舞会邀请函 [广西TH3]'): {
        '满目虚无的红',
        '未见之城',
        '蕾米莉亚好像若无其事的下午',
    },
    # https://www.dizzylab.net/d/SRCP02/
    ('[SORRICOP]', '2024.10.04 [SRCP-02] 魂蝶花葬记 ~ The Blossom of Everlasting [广西TH5]'): {
        'intro ~ 得闲趣话',
        '异闻循迹',
        '梦随樱逝',
        '剑断我执',
        '魂蝶花葬 ~ 死别',
        '春风吹雪',
    },
    # https://www.dizzylab.net/d/SRCP03/
    ('[SORRICOP]', '2025.07.19 [SRCP-03] 须臾的悖论 ~ Immortal Dialectics ~'): {
        '月难！心跳加速是病啊',
        '一隅长明',
        '须臾的悖论 ~ Immortal Dialectics ~',
        '月难！/)_/)心跳(〇` ﾟДﾟ)加速是病啊',
    },
    # https://www.dizzylab.net/d/SS-TH-001/
    ('[Sociable State]', '2024.10.25 [SS-TH-001] 流彩桜華 [PartyNight×广州TH-游剧天P2]'): {
        '揽月',
        '飘上月球，不死之烟',
    },
    # https://thwiki.cc/仲夏摇篮曲
    ('[Static World]', '2024.08.18 [SWCD-018] 仲夏摇篮曲 [魅知幻想 星辉琉璃]'): {
        '给予我的信',
        '飞越蔚蓝之空',
        '林间小憩',
        '回忆有你的时光',
    },
    # https://store.steampowered.com/app/929350/__Fantastic_Danmaku_Festival_Soundtrack/
    ('[东方幕华祭制作组]', '2014.07.19 東方幕華祭 紅月篇 OST [COMIDAY14]'): {
        '散落的烛光 ～ Candlelight',
        '妖精背水一战 ～ A dare',
        '东方梦之馆 ～ East castle',
        '风卷残云 ～ Kongfu storm',
        '沉睡中的大图书馆 ～ The library in silence',
        '华丽的恶魔之舞 ～ The little devil dance',
        '时钟走廊 ～ Flowing time',
        '钟楼战场 ～ Bell tower',
        '绯月之主 ～ The master of red moon',
        '无尽的命运 ～ Endless fate',
        '幕华祭  ～红月编～',
        '百年少女怪谈 ～ The mystery',
        '淋满鲜血的还有谁呢 ～ Who care',
    },
    # https://thwiki.cc/index.php?setlang=ja&title=東方幕華祭_春雪篇_ORIGINAL_SOUNDTRACK
    ('[东方幕华祭制作组]', '2019.04.05 東東方幕華祭 春雪篇 OST'): {
        '常世之乡',
        '无穷无尽的白色',
        '梦境演剧',
        '喜欢西洋乐的人偶们',
        '看不破的人偶剧',
        '春岚',
        '通向往生之界的阶梯',
        '极乐庄严',
        '狂樱之舞',
        '生死之间花吹雪',
        '飞舞吧！永世的繁花',
        '幕华祭~春雪篇~',
        '感知崩坏的空间',
        '人类与妖怪的铁幕',
        '月下花见急行',
        '地狱行乐',
    },
    # https://store.steampowered.com/app/4062010/__OST/?l=schinese
    ('[东方幕华祭制作组]', '2025.10.05 東方幕華祭 永夜篇 OST'): {
        '萤之光迹',
        '竹林突围',
        '历史不会简单被忘记',
        '岁月不待 一日千秋',
        '森罗万象',
        '归旅',
        '人类的勇气',
        '幕华祭 ~永夜篇~',
        '莫里茨的游戏',
        '就这样沉入黑暗吧',
        '噩梦降临',
        '人类的勇气 永琳阶段',
        '人类的勇气 辉夜阶段',
    },
    # https://store.steampowered.com/app/1259650/Elegant_Impermanence_of_Sakura_Soundtrack/
    ('[东方祈华梦制作组]', '2020.04.16 东方祈华梦 ～ Elegant Impermanence of Sakura. Soundtrack'): {
        '意祈华思 夜星明梦',
        '幽竹远梦',
        '辉夜的指引',
        '失色的镜像世界',
        '林间烟雨小令',
        '彼岸之云 结界之梦',
        '魔女和亡灵的★Dance Party',
        '万华镜之箱',
        '樱花飞舞的浅间神社',
        '徒名草之道 ～神宫寺祈前哨战～',
        '华彩飞扬\u3000～ Indomitable Kagura',
        '一念的繁华',
        '春彩动荡之寂 ～盛樱之世～',
        '灵空猝灭雨',
        '落花残响',
        '幻想乡的神隐少女',
    },
    # https://store.steampowered.com/app/1259650/Elegant_Impermanence_of_Sakura_Soundtrack/
    ('[东方祈华梦制作组]', '2020.05.01 [MXB-007] 浅间密约 ～ Another Dream'): {
        '意祈华思 夜星明梦',
        '幽竹远梦',
        '辉夜的指引',
        '失色的镜像世界',
        '林间烟雨小令',
        '彼岸之云 结界之梦',
        '魔女和亡灵的★Dance Party',
        '万华镜之箱',
        '樱花飞舞的浅间神社',
        '徒名草之道 ～神宫寺祈前哨战～',
        '华彩飞扬\u3000～ Indomitable Kagura',
        '一念的繁华',
        '春彩动荡之寂 ～盛樱之世～',
        '灵空猝灭雨',
        '落花残响',
        '幻想乡的神隐少女',
        '参见樱华院大人',
        '人间之里的秋雾',
        '朦胧夜雨 彼岸幽樱',
        '不存在仙人的空之岛',
        '樱华院静前哨战',
        '八岳山的破晓',
    },
    # https://store.steampowered.com/bundle/26151/Mystias_Izakaya_Complete_OST_Bundle/
    ('[二色幽紫蝶] Dichroic Purpilion', '2021.07.30 東方夜雀食堂 - OST原聲音樂集1'): {
        '静谧的妖怪栖息之地 - 兽道Theme',
        '今天的博丽神社也依然庄严而冷清 - 博丽神社Theme',
        '舒适午后的微甜红茶 - 红魔馆Theme',
        '无限延伸的绿色秘境 - 迷途竹林Theme',
        '破败与凋零 - 白玉楼Theme',
        '人类的入眠，妖怪的起床 - 兽道气氛Lv1',
        '即使是妖怪也要努力打工！ - 兽道气氛Lv2',
        '妖怪食之祭 - 兽道气氛Lv3',
        '笔记中的七色世界',
        '紧张，但没有完全紧张',
        '令人愉快的话语',
        '咆哮吧！我灵魂中的声音！',
        '深不见底的食欲',
        '尘埃落定',
        '满身创痍 - Game Over',
    },
    # https://store.steampowered.com/bundle/26151/Mystias_Izakaya_Complete_OST_Bundle/
    ('[二色幽紫蝶] Dichroic Purpilion', '2021.12.19 東方夜雀食堂 - OST原聲音樂集2'): {
        '人间之里-三五成群',
        '人间之里-接踵而至',
        '人间之里-人山人海',
        '博丽神社-惊闻客来',
        '博丽神社-稀客盈门',
        '博丽神社-座无虚席',
        '红魔馆-饮酒品肴',
        '红魔馆-色味共赏',
        '红魔馆-遂心快意',
        '迷途竹林-轻车熟路',
        '迷途竹林-欢欣狂舞',
        '白玉楼-一步之遥',
    },
    # https://store.steampowered.com/app/1982490/__OST3/?l=tchinese
    ('[二色幽紫蝶] Dichroic Purpilion', '2022.05.14 東方夜雀食堂 - OST原聲音樂集3'): {
        '神仙都爱俺们屯儿',
        '妖怪之山-初见方园',
        '妖怪之山-临风对月',
        '妖怪之山-一览众小',
        '魔女武踏会上的蘑女舞踏烩',
        '魔法之森-孤芳自赏',
        '魔法之森-花鸟庭园',
        '魔法之森-闲适静谧',
        '血池地狱-吞天噬地',
        '去旧地狱街道吃香喝辣！',
        '旧地狱-暗里寻光',
        '旧地狱-柳暗花明',
        '旧地狱-万紫千红',
        '在地灵殿动物园投食撸宠',
        '地灵殿-废狱笙歌',
        '地灵殿-独舞成影',
        '地灵殿-众舞成画',
        '料理大赛-半忧半喜',
        '料理大赛-亦赛亦闹',
        '料理大赛-一将功成',
        '吞天噬地(未采用稿01)',
        '吞天噬地(未采用稿02)',
        '吞天噬地(未采用稿03)',
        '在地灵殿动物园投食撸宠(保留版本)',
    },
    # https://store.steampowered.com/app/2194750/?l=tchinese
    ('[二色幽紫蝶] Dichroic Purpilion', '2022.11.18 東方夜雀食堂 - OST原聲音樂集4'): {
        '命莲寺-青山绿瓦',
        '命莲寺-丹书黄卷',
        '命莲寺-古佛新衣',
        '清修苦心，得道飞升',
        '神灵庙-绀碧一隅',
        '神灵庙-树静风轻',
        '神灵庙-苔痕皆缘',
        '秋意纷至，灯火阑珊',
        '摇滚大赛-入道之魂',
        '摇滚大赛-船灵之魂',
        '摇滚大赛-虎刹之魂',
        '国宴大赛-殚精竭虑',
        '国宴大赛-精雕细琢',
        '国宴大赛-超我大成',
    },
    # https://store.steampowered.com/app/2534540?l=schinese
    ('[二色幽紫蝶] Dichroic Purpilion', '2023.07.28 东方妖精武踏会 - OST原声音乐集'): {
        '道中01 - 可爱的大战争叠奏曲',
        '决战01 - 前所未见的噩梦世界',
        '决战02 - 再也进不去的门',
        'BOSS战00 - 食我大手电筒啦！',
        'BOSS战01 - 少女二色绮想曲',
        'BOSS战02 - 星之恋色MasterSpark!!!',
        'BOSS战03 - 女仆与血之怀表',
        'BOSS战04 - 东方妖妖妖妖梦',
        'BOSS战05 - 笼中灰姑娘的狂气之瞳',
        'BOSS战06 - 信仰着不存在之人的少女望见的日本原风景',
        'BOSS战07 - 废狱摇篮曲',
        'BOSS战08 - 大神神话传',
        'ExBOSS战01 - 潘地漫尼克星球',
        'ExBOSS战02 - 两个世界',
        'UI界面01 - 雪月樱花之国',
        'UI界面02 - 活泼的纯情小姑娘',
    },
    # https://store.steampowered.com/app/2797450/__5/?l=schinese
    ('[二色幽紫蝶] Dichroic Purpilion', '2024.02.12 東方夜雀食堂 - OST原聲音樂集5'): {
        '草帽花农与金色阳光',
        '太阳花田-一叶入梦',
        '太阳花田-花团锦簇',
        '太阳花田-金色交响',
        '全员恶人',
        '辉针城-悠然来声',
        '辉针城-回转加速',
        '辉针城-无垠狂飙',
        '吾令徐徐春风!吹散无尽幽暗!',
        '你所不知道的幽谷兰香',
        '魔界-奇花异卉',
        '无秽的彼方',
        '月都-风起萧瑟',
        '困兽之斗，天罗地网！',
    },
    # https://www.bilibili.com/video/BV1U84y1D7q3/
    ('[旧雨忆梦幻想乐团]', '2023.09.23 [JYYM-01] 東方山海傳 ~ the Potential Crisis'): {
        '山海汇聚~Story of Nightmare',
        '冲破结界的骇浪~Connect the bridge of the continent',
        '绽放的净土之花~Purify filth',
        '古瓷的妖兽祭',
        '审判世界的神魔之眼',
        '幽匿之风 炽焰之月',
        '难逃的雷神之庙~The thunder',
        '苍之山海~power of jadeite',
        '无上之龙的闪耀之鳞~The strongest brain',
        '现实与虚假之路',
        '山海汇聚，不死鸟的重生~Nirvana is reborn！',
        '幻想乡的存亡时刻~to be，or not to be',
        '少女曾见的古瓷之山巅~Mountain And Sea',
        '血月降至！狐神降临之夜',
        '真相终将破晓',
        '山海终将汇聚~Story End',
        '再一次，为世界的美好而战吧',
    },
    # https://rickyrister.bandcamp.com/album/a-journey-of-reminiscences
    ('[明京梦纪行制作组]', '2023.10.06 明京梦纪行 ～ A Journey of Reminiscences'): {
        '梦纪行',
        '化鸟之诗，流离于梦之旅路',
        '海波逐风流',
        '祇园花行路',
        '华尽染分恋语录 ～ A Fruitless Love',
        '雨月尽头的妄樱',
        '春花长留望月庵 ～ Drowning in the Spring Sky',
        '童戏御谣曲',
        '梁尘醉狂歌 ～ A Lifelong Indulgence',
        '白峰漫想谭',
        '鞠壶自有四方天 ～ アリ、ヤウ、オウ！',
        '阳炎涅槃忏悔咒 ～ Confession\xa0or\xa0Curse',
        '荣花之色，明灭于幻之海空',
        '日暮归倦鸟 ～ Meteor Dream',
    },
    # https://thwiki.cc/柳畔星夜逝_~_东方夏夜祭_Original_Sound_Track
    ('[梦现彼岸结界社]', '2017.07.08 [MXB-C01] 柳畔星夜逝 ~ 东方夏夜祭 Original Sound Track [上海TH08]'): {
        '被遗忘的久远星辉',
        '宁静夏夜的微风',
        '喧嚣吧！在这不眠之夜',
        '疾风闪电',
        '木灵们的夏夜祭',
        '青柳传说',
        '镜中的幻像',
        '记忆中遥远的星星',
        '银河的彼方',
        '闪耀在世界尽头',
        '晚星之梦',
        '来自仙界的新风',
        '风中花，雪中月',
        '满身疮痍',
    },
    # https://thwiki.cc/朝花暮留香_~_Departure,_Fragrant_Conformist./附带故事
    ('[梦现彼岸结界社]', '2019.08.17 [MXB-005] 朝花暮留香 ～ Departure, Fragrant Conformist [上海TH10]'): {
        '狭界的飘扬\u3000～ Liberal Liberty',
        '雾里看花、不思量',
        '灵知的太阳信仰\u3000～ Flowery Fusion',
        '镜中的幻象',
        '无何有之乡\u3000～ Deep Garden',
        '落红的幽响',
        '曲水流觞\u3000～ Genteel Ritual',
        '群青的怅惘',
        '镜花水月、自难忘',
    },
    # https://www.dizzylab.net/d/MhT_TH007/
    ('[疯帽子茶会] Mad hatter Tea', '2018.10.05 [MhT·TH-007] 白脱怀表 [真·東方遊劇天]'): {
        '漫步幻想乡',
        '红',
        '漫步在幻想乡',
    },
    # https://www.dizzylab.net/d/MhT_TH008/
    ('[疯帽子茶会] Mad hatter Tea', '2018.12.15 [MhT·TH-008] 星夜神话 [COMICUP23]'): {
        '星夜神话',
        '没人猜的谜语',
        '萤火之森',
    },
    # https://www.dizzylab.net/d/MhT_TH009/
    ('[疯帽子茶会] Mad hatter Tea', '2019.05.25 [MhT·TH-009] 羽衣清歌 [京华万象展1]'): {
        '克鲁苏图童话(Remix ver.)',
        '华胥梦魂 -乱-',
        '乐游空海',
        '傀儡师会梦见杀人兔吗？',
        '天官风角秘盘 -木符-',
        '献给深红之王的七重奏',
    },
    # https://www.dizzylab.net/d/MhT_TH010/
    ('[疯帽子茶会] Mad hatter Tea', '2019.08.17 [MhT·TH-010] 心觉幻恋 [上海TH10]'): {
        '少女废墟旅行~Hellaby',
        '心觉幻恋-误线',
        '心觉幻恋 -悟限',
        '祂的乐章',
        '为自由平等而旅行',
    },
    # https://www.dizzylab.net/d/CLMHT-01/
    ('[疯帽子茶会] Mad hatter Tea', '2019.12.21 [CLMHT-01] 千年战争～iek loin staim haf il dis o-del al [COMICUP25]'): {
        '千年战争～iek loin staim haf il dis o-del al',
        '历火 ～Rondo of Nostalgia',
    },
    # https://www.dizzylab.net/d/MhT_TH014/
    ('[疯帽子茶会] Mad hatter Tea', '2021.06.12 [MhT·TH-014] 祈风 [COMICUP28]'): {
        '风之诗',
        '笼中鸟',
        '遥远之星',
        '绵绵无绝期',
    },
    # https://www.dizzylab.net/d/MhT_TH015/
    ('[疯帽子茶会] Mad hatter Tea', '2021.08.07 [MhT·TH-015] Shion [上海TH11]'): {
        '无何有之乡·静',
        '少女废墟旅行（JP Ver.）',
        '摇光',
        '无何有之乡·静 INST',
        '少女废墟旅行 INST',
    },
    # https://www.dizzylab.net/d/MhT-TH018/
    ('[疯帽子茶会] Mad hatter Tea', '2022.09.30 [MhT·TH-018] 眷恋'): {
        '幽兰',
        '落樱旅程',
        '幽兰inst',
        '落樱旅程inst',
    },
    # https://www.dizzylab.net/d/MhT-TH019/
    ('[疯帽子茶会] Mad hatter Tea', '2023.07.23 [MhT-TH019] 絢夢のワルツ~Valzer da sogno [广西TH3]'): {
        '伊甸花园～Hortus Eden～',
        '你是如此可爱',
        '腐烂苹果',
        '伊甸花园～Hortus Eden～ offvoice.ver',
        '你是如此可爱 offvoice.ver',
    },
    # https://store.steampowered.com/app/2082910/OST/
    ('[车万石]', '2022.07.19 东方心之解束 OST'): {
        '帕琪的忧伤',
        '日常的红茶馆',
        '雾之湖畔',
        '欢乐的芙兰',
        '人间之里的约会',
        '露米娅的饭点',
        '两人的庆典',
        '封锁',
        '烦恼冻结',
        '虚幻与现实的缔造者',
        '比蔷薇更红的希望',
        '永恒的誓言守护者',
    },
    # https://store.steampowered.com/app/2269160/__Abyss_Soul_Lotus_Soundtrack/?l=tchinese
    ('[雨夜枫雪制作组]', '2023.02.03 东方雪莲华 ～ Abyss Soul Lotus. Soundtrack'): {
        '盛开于净土之莲 (Title Theme)',
        '冰与雪的灵动 (Boss 1 Theme)',
        '悔恨凝结之路 (Stage 2 Theme)',
        '开不尽的雪莲华 (Stage 3 Theme)',
        '少女所见的深渊风景 (Stage 4 Theme)',
        '沉没八万由旬的叹息 (Stage 5 Theme)',
        '以太虚无论 (Boss 5 Theme)',
        '绽放在世界终焉 (LSC Theme)',
        '待春花烂漫 (Staff Roll Theme)',
        '被遗忘的无名者 (Stage Extra Theme)',
        '不灭之魂 ～ Everlasting Volition (Boss Extra Theme)',
        '盛开于净土之莲 (Beta Version)',
        '冰与雪的灵动 (Beta Version)',
        '悔恨凝结之路 (Beta Version)',
        '开不尽的雪莲华 (Beta Version)',
        '绽放在世界终焉 (Unused Version)',
        '明日为终结之日 (Unused Version)',
        '最后的阿修罗 ～ Forgotten Tears (Unused Version)',
    },
    # https://store.steampowered.com/app/3276850/__Immortal_Immanuel_Soundtrack/?l=tchinese
    ('[雾雨威Channel]', '2025.01.17 東方资志疏OST'): {
        '织梦呓 ~ Unobservable Undercurrent.',
        '花径醉尘，酒香翩跹',
        '瓿中游龙',
        '勿忘草于原野盛开',
        '丛云之上无顶天',
        '血红的惊雷',
        '万钧肝胆挞神鸣 ~ Godless God.',
        '破碎宫殿的残响',
        '云霄白狐乐园',
        '废土田园诗 ~ Barriers between Hearts.',
        '通讯中断 ~ Player‘s Score.',
    },
    # https://www.dizzylab.net/d/THgu-05/
    ('[鸽屋谷]', '2022.10.03 回忆京都 [深圳TH4]'): {
        '神隐',
        '逢魔之时',
        '罗生门',
    },
}

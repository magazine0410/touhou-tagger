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
    "koumakyou":      "Koumakan",
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
}

_TITLE_OVERRIDES: dict[str, str] = {
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

# Phrase-level overrides: tuple of MeCab surface strings → Romaji.
# Applied before loanword matching, longest-match-first (up to 4 tokens).
# Use this when MeCab splits a known compound into pieces that loanword
# lookup cannot reassemble (e.g. a coined place name with no UniDic entry).
# Keys are tuples of exact surface forms as MeCab produces them.
# Example:
#   ("幻想", "郷"): "Gensokyo",
_PHRASE_OVERRIDES: dict[tuple, str] = {
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

    # T10 subtitle — yojijukugo read as all on'yomi
    ("前", "退", "後", "進"):    "Zentaikoushin",    # 前 misread as "mae"
}

export interface CuteThinkingFrame {
  readonly emoji: string;
  readonly text: string;
}

const IDLE_FRAME: CuteThinkingFrame = {
  emoji: '🌸',
  text: 'bereit zum Bauen',
};

const CUTE_THINKING_EMOJIS = [
  '🤖💭',
  '🧸✨',
  '🐣🔎',
  '🐤🌾',
  '🐥💛',
  '🦊🧩',
  '🐙⚙️',
  '🛠️🌷',
  '🧪🍬',
  '🚀💌',
] as const;

const CUTE_CHICK_THINKING_TEXTS = [
  'Küken piepst und sortiert den Auftrag',
  'Küken sucht Körner im Repo',
  'Piep piep, ich prüfe echte Dateien',
  'Küken pickt passende Pattern heraus',
  'Küken schreibt vorsichtig Code',
  'Piep, ich lasse die Runtime arbeiten',
  'Küken schaut nach Tests und Guards',
  'Küken hält den Draft PR warm',
  'Piep, ich suche keinen Fake-Fortschritt',
  'Küken hat fast fertig gepiepst',
] as const;

export const CUTE_KAOMOJI_FRAMES = [
  '(^_^)',
  '(^o^)',
  '＼(^^)／',
  '＼(^-^)／',
  '＼(^_^)／',
  '(^ー^)',
  '(^○^)',
  '(￣ー￣)',
  '(⌒‐⌒)',
  'd=(^o^)=b',
  'o(^o^)o',
  'p(^^)q',
  'p(^-^)q',
  '( ﾟーﾟ)',
  '(　＾∀＾)',
  '(　＾▽＾)',
  '( ＾ω＾ )',
  '(　＾ω＾)',
  '(　＾Д＾)',
  '( ´;ﾟ;∀;ﾟ;)',
  '( ´,_ゝ`)',
  '( ￣▽￣)',
  '( ￣ー￣)',
  '( ´ー`)',
  '( ´∀｀ )b',
  '( ´∀`)',
  '( ´・∀・｀)',
  '(*^ー^)ノ♪',
  '(*ﾟ∀ﾟ人ﾟ∀ﾟ*)♪',
  '(*≧∀≦)',
  '(ﾟ∀ﾟ 三 ﾟ∀ﾟ)',
  '(o^－^o)',
  'ヽ(´∀｀≡´∀｀)ﾉ',
  'Ｏ(≧∇≦)Ｏ',
  '((T_T))',
  '( ｡ﾟДﾟ｡)',
  '( ´-｀)',
  '(´・c_・`)',
  '゜゜(´O｀)°゜',
  'Σ(＞Д＜)',
  '(@_@)',
  '(@_@;)',
  '(￣O￣)',
  '(ノ゜ο゜)ノ',
  '(ﾟДﾟ≡ﾟДﾟ)ﾞ?',
  'Σヽ(ﾟ∀ﾟ；)',
  '＼(◎o◎)／',
  '(・・;)',
  '(^_^;)',
  '( ;´･ω･`)',
  '(  -_・)?',
  '(;＞_＜;)',
  '( ;｀Д´)',
  '(ノ-_-)ノ~┻━┻',
  '(Ｏﾟ皿ﾟＯ)',
  '(*｀ω´*)',
  '(＃ﾟДﾟ)ﾉ',
  '(((￣へ￣井)',
  '(ー。ー#)',
  '(｡-｀へ´-｡)',
  '(⌒0⌒)／~~',
  '(-_-)/~~~',
  '(＠＾＾＠)／',
  '(* ´ ▽ ` *)ﾉ',
  '(*^ーﾟ)ﾉ',
  '(^ー゜)ノ',
  '(*￣▽￣)ノ~~ ♪',
  '(^人^)',
  '((φ(￣ー￣  )',
  '(-.-)y-~',
  '(-。-)y-~',
  '(;_;)/~~~',
  '(-.-)ノ⌒-~',
  '(。-_-。)♪',
  'φ(．．)',
  '(/--)/',
  '(^з^)-☆',
  '(〃´ー｀人´ー｀〃)',
  'ヽ(●´ε｀●)ノ',
  'ヽ(o´3`o)ﾉ',
  '( ﾟ∀ﾟ)人(ﾟ∀ﾟ )',
  '(^3^)/',
  '(*⌒３⌒*)',
  '(≡・x・≡)',
  '(=^ェ^=)',
  '(-)_(-)',
  '(ФωФ)',
  'U^ェ^U',
  '⌒(ё)⌒',
  '￣(=∵=)￣',
] as const;

export const CUTE_THINKING_FRAMES: readonly CuteThinkingFrame[] = CUTE_CHICK_THINKING_TEXTS.map((text, index) => ({
  emoji: CUTE_THINKING_EMOJIS[index % CUTE_THINKING_EMOJIS.length],
  text,
}));

export function normalizeThinkingFrameIndex(index: number, total = CUTE_THINKING_FRAMES.length): number {
  if (!Number.isFinite(index) || index < 0) return 0;
  if (!Number.isFinite(total) || total <= 0) return 0;
  return Math.floor(index) % total;
}

export function getCuteThinkingFrame(index: number, active: boolean): CuteThinkingFrame {
  if (!active) return IDLE_FRAME;
  return CUTE_THINKING_FRAMES[normalizeThinkingFrameIndex(index)] ?? IDLE_FRAME;
}

export function getCuteKaomojiFrame(index: number): string {
  return CUTE_KAOMOJI_FRAMES[normalizeThinkingFrameIndex(index * 7 + 3, CUTE_KAOMOJI_FRAMES.length)] ?? CUTE_KAOMOJI_FRAMES[0];
}

export function formatCuteThinkingLabel(args: {
  readonly index: number;
  readonly active: boolean;
  readonly status?: string;
}): string {
  const frame = getCuteThinkingFrame(args.index, args.active);
  const kaomoji = getCuteKaomojiFrame(args.index);
  if (!args.active) return `${frame.emoji} ${kaomoji} ${frame.text}`;
  const cleanStatus = args.status?.trim();
  const suffix = cleanStatus ? ` · ${cleanStatus}` : '';
  return `${frame.emoji} ${kaomoji} ${frame.text}...${suffix}`;
}

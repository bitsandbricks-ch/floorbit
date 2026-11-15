// Standard German for Germany and Austria, made from the Swiss texts: the two differ in writing
// "ß" where Switzerland writes "ss". Making it here keeps one set of German files to maintain.
// Only whole words from this list change; add a word here when a new text needs it.
const SHARP_S: [RegExp, string][] = [
  [/(^|[^A-Za-zÄÖÜäöü])([Gg])ross/g, '$1$2roß'],
  [/([Gg])rösse/g, '$1röße'],
  [/([Ss])chliess/g, '$1chließ'],
  [/([Dd])raussen/g, '$1raußen'],
  [/(^|[^A-Za-zÄÖÜäöü])([Aa])ussen/g, '$1$2ußen'],
  [/(^|[^A-Za-zÄÖÜäöü])([Aa])usser/g, '$1$2ußer'],
  [/(^|[^A-Za-zÄÖÜäöü])([Ww])eiss(t?)(?![A-Za-zäöü])/g, '$1$2eiß$3'],
  [/([Ss])trasse/g, '$1traße'],
  [/(^|[^A-Za-zÄÖÜäöü])([Ff])uss(?![A-Za-zäöü])/g, '$1$2uß'],
  [/([Gg])emäss/g, '$1emäß'],
  [/([Mm])ässig/g, '$1äßig'],
  [/([Hh])eiss/g, '$1eiß'],
  [/([Ss])pass(?![A-Za-zäöü])/g, '$1paß'],
  [/([Gg])russ/g, '$1ruß'],
  [/(^|[^A-Za-zÄÖÜäöü])([Bb])loss(?![A-Za-zäöü])/g, '$1$2loß'],
]

/** One Swiss German text in German German spelling. Placeholders ({{name}}) are left alone. */
export function toGermany(text: string): string {
  return text
    .split(/(\{\{[^}]*\}\})/)
    .map((part) => (part.startsWith('{{') ? part : SHARP_S.reduce((s, [re, to]) => s.replace(re, to), part)))
    .join('')
}

type Texts = Record<string, unknown>

/** Every text in a bundle, converted; keys stay as they are. */
export function germanyBundle(swiss: Texts): Texts {
  const walk = (v: unknown): unknown => {
    if (typeof v === 'string') return toGermany(v)
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)]))
    return v
  }
  return walk(swiss) as Texts
}

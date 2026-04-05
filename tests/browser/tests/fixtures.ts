export type CodeServerSource =
  | { url: string; image?: never }
  | { image: string; url?: never };

export type ConfigFixtures = {
  connectCDP: false | number;
  codeServerSource: CodeServerSource;
};

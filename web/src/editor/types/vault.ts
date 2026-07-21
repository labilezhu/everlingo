export interface LangsResp {
  vaults: string[];
  count: number;
}

export interface Entry {
  name: string;
  path: string;
  type: 'dir' | 'file';
  children?: Entry[];
}

export interface TreeResp {
  path: string;
  depth: number;
  entries: Entry[];
}

export interface ReadResp {
  path: string;
  content: string;
  size_bytes: number;
}

export interface WriteResp {
  ok: boolean;
  path: string;
}

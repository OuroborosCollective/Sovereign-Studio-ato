export interface ContractField {
  readonly name: string;
  readonly type: string;
  readonly required: boolean;
}

export interface ContractSurface {
  readonly name: string;
  readonly fields: readonly ContractField[];
}

export interface ContractDriftFinding {
  readonly surface: string;
  readonly field: string;
  readonly kind: 'missing' | 'unexpected' | 'type-mismatch' | 'requiredness-mismatch';
  readonly expected?: string;
  readonly observed?: string;
}

export interface ContractDriftReport {
  readonly aligned: boolean;
  readonly findings: readonly ContractDriftFinding[];
  readonly summary: string;
}

function fieldMap(surface: ContractSurface): Map<string, ContractField> {
  return new Map(surface.fields.map((field) => [field.name, field]));
}

export function compareContractSurfaces(
  authoritative: ContractSurface,
  candidates: readonly ContractSurface[],
): ContractDriftReport {
  const expected = fieldMap(authoritative);
  const findings: ContractDriftFinding[] = [];

  for (const candidate of candidates) {
    const observed = fieldMap(candidate);
    for (const [name, field] of expected) {
      const actual = observed.get(name);
      if (!actual) {
        findings.push({ surface: candidate.name, field: name, kind: 'missing', expected: field.type });
        continue;
      }
      if (actual.type !== field.type) {
        findings.push({ surface: candidate.name, field: name, kind: 'type-mismatch', expected: field.type, observed: actual.type });
      }
      if (actual.required !== field.required) {
        findings.push({ surface: candidate.name, field: name, kind: 'requiredness-mismatch', expected: String(field.required), observed: String(actual.required) });
      }
    }
    for (const [name, field] of observed) {
      if (!expected.has(name)) findings.push({ surface: candidate.name, field: name, kind: 'unexpected', observed: field.type });
    }
  }

  return {
    aligned: findings.length === 0,
    findings,
    summary: findings.length === 0
      ? `${candidates.length} contract surface(s) align with ${authoritative.name}.`
      : `${findings.length} contract drift finding(s) against ${authoritative.name}.`,
  };
}

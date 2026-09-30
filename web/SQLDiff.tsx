import { diffLines } from "diff";
export function SQLDiff({
  original,
  candidate,
  verified,
}: {
  original: string;
  candidate: string;
  verified: boolean;
}) {
  const changes = diffLines(original, candidate);
  return (
    <>
      <div className="sql-diff">
        <div>
          <h3>Original SELECT</h3>
          <pre>
            {changes
              .filter((c) => !c.added)
              .map((c, i) => (
                <span key={i} className={c.removed ? "diff-removed" : ""}>
                  {c.value}
                </span>
              ))}
          </pre>
        </div>
        <div>
          <h3>{verified ? "Verified candidate" : "Retain original SELECT"}</h3>
          <pre>
            {changes
              .filter((c) => !c.removed)
              .map((c, i) => (
                <span key={i} className={c.added ? "diff-added" : ""}>
                  {c.value}
                </span>
              ))}
          </pre>
        </div>
      </div>
      {original === candidate && (
        <p className="diff-note">
          The SELECT is unchanged. Any measured benefit comes from the tested
          index.
        </p>
      )}
    </>
  );
}

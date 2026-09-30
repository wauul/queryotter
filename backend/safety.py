import sqlglot
from sqlglot import exp

class Unsupported(ValueError): pass

ALLOWED_FUNCS = {'COUNT','SUM','AVG','MIN','MAX','COALESCE','LOWER','UPPER','CAST','EXTRACT','DATE_TRUNC','ABS','ROUND','NULLIF'}
TABLES = {'orders','customers','items'}

def validate_query(sql: str, tables=TABLES):
    if len(sql) > 12000: raise Unsupported('SQL exceeds the 12,000 character limit.')
    try: roots=sqlglot.parse(sql,read='postgres')
    except sqlglot.errors.ParseError: raise Unsupported('SQL could not be parsed as PostgreSQL.') from None
    if len(roots)!=1 or not isinstance(roots[0],exp.Select): raise Unsupported('Only one SELECT statement, including SELECT-only CTEs, is supported.')
    root=roots[0]
    if root.find(exp.Into) or root.find(exp.Lock) or root.args.get('with_') and root.args['with_'].args.get('recursive'):
        raise Unsupported('SELECT INTO, locking and recursive CTEs are unsupported.')
    for n in root.walk():
        if isinstance(n,(exp.Insert,exp.Delete,exp.Update,exp.Command,exp.Create,exp.Drop,exp.Union,exp.Window)):
            raise Unsupported('Writes, set operations, commands and window functions are outside supported scope.')
        if isinstance(n,exp.Func):
            name = n.name.upper() if isinstance(n,exp.Anonymous) else n.sql_name()
            if name not in ALLOWED_FUNCS: raise Unsupported(f'Function {name} is not on the safe immutable-function allowlist.')
    ctes={c.alias for c in root.find_all(exp.CTE)}
    for t in root.find_all(exp.Table):
        if t.db or t.catalog or t.name not in tables|ctes: raise Unsupported('Only approved, unqualified experiment tables can be queried.')
    for select in root.find_all(exp.Select):
        if select.args.get('limit') or select.args.get('offset'):
            order=select.args.get('order')
            if not order: raise Unsupported('LIMIT/OFFSET requires deterministic ORDER BY with a unique tie-breaker.')
            ordered={n.this.name for n in order.expressions if isinstance(n.this,exp.Column)}
            groups={n.name for n in select.args.get('group',exp.Group()).expressions if isinstance(n,exp.Column)}
            joined=bool(select.args.get('joins'))
            ids=[n for n in order.expressions if isinstance(n.this,exp.Column) and n.this.name in {'id','item_id'}]
            if not (groups and groups<=ordered) and (not ids or joined and len(ids)<2):
                # customer joins have a many-to-one FK, so orders.id is unique
                if not (joined and 'items' not in {t.name for t in select.find_all(exp.Table)} and ids):
                    raise Unsupported('ORDER BY does not establish a supported unique tie-breaker; add a primary key.')
    # ORDER BY without LIMIT also needs uniqueness to compare row sequences reliably.
    order=root.args.get('order')
    if order and not root.args.get('limit'):
        cols={e.this.name for e in order.expressions if isinstance(e.this,exp.Column)}
        groups={n.name for n in root.args.get('group',exp.Group()).expressions if isinstance(n,exp.Column)}
        if not ({'id','item_id'} & cols or groups and groups<=cols): raise Unsupported('Ambiguous output ordering is not supported.')
    return root.sql(dialect='postgres',comments=False,pretty=True)

def validate_index(sql: str):
    try: root=sqlglot.parse_one(sql,read='postgres')
    except Exception: raise Unsupported('Invalid index statement.') from None
    if not isinstance(root,exp.Create) or root.args.get('kind')!='INDEX' or root.args.get('unique'):
        raise Unsupported('Only non-unique CREATE INDEX experiments are allowed.')
    index=root.this
    table=index.args.get('table')
    if not isinstance(table,exp.Table) or table.name not in TABLES or table.db or table.catalog:
        raise Unsupported('Index target must be an approved disposable table.')
    if root.find(exp.Func) or root.find(exp.Select): raise Unsupported('Expression or subquery indexes are unsupported.')
    if ';' in sql.rstrip(';'): raise Unsupported('Multiple index statements are forbidden.')
    return root.sql(dialect='postgres',comments=False)

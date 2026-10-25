import cytoscape from 'cytoscape'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, img } from '../api'
import { Lane, Modal, Tip, titleCase } from '../ui'

const KIND: Record<string, string> = {
  faculty: 'same faculty', faculty_id: 'same faculty ID', faculty_pan: 'same PAN + date of birth', photo: 'same photo', doc_sha: 'identical file',
  ref_fire_noc: 'same fire certificate', ref_occupancy_certificate: 'same occupancy certificate', ref_affidavit_2: 'same e-stamp paper',
  ref_audited_statement: 'same UDIN', ref_ter_receipt: 'same fee receipt',
}
const LANE_COLOR: Record<string, string> = { red: '#b23a2e', amber: '#c77a1a', green: '#2e7d32' }
const short = (s: string) => titleCase(s).replace(/ (Institute|College) of .*/, '').replace(/ Institute of Technology$/, '')

function edgeLabel(e: any) {
  const people = e.items.filter((i: any) => i.type.startsWith('faculty'))
  const parts = Object.entries(e.kinds).filter(([k]) => !k.startsWith('faculty')).map(([k, v]) => `${KIND[k] || k}${Number(v) > 1 ? ` ×${v}` : ''}`)
  if (people.length) {
    const rows = new Set(people.flatMap((i: any) => i.members.map((m: any) => `${m.permanent_id}:${m.page}`)))
    parts.unshift(`${Math.round(rows.size / 2)} shared faculty`)
  }
  return parts.join(' · ')
}

/** Each linked group gets its own space; members sit on a circle. Stable and never overlapping. */
function arrange(nodes: any[], edges: any[]) {
  const ids = nodes.map((n) => n.id)
  const parent: Record<string, string> = Object.fromEntries(ids.map((i) => [i, i]))
  const find = (x: string): string => (parent[x] === x ? x : (parent[x] = find(parent[x])))
  edges.forEach((e) => { if (parent[e.source] && parent[e.target]) parent[find(e.source)] = find(e.target) })
  const groups: Record<string, string[]> = {}
  ids.forEach((i) => (groups[find(i)] ||= []).push(i))
  const comps = Object.values(groups).sort((a, b) => b.length - a.length)
  const cols = Math.max(1, Math.ceil(Math.sqrt(comps.length * 1.6)))
  const pos: Record<string, { x: number; y: number }> = {}
  comps.forEach((c, k) => {
    const cx = (k % cols) * 460, cy = Math.floor(k / cols) * 360
    const r = c.length === 1 ? 0 : c.length === 2 ? 150 : 170
    c.forEach((id, j) => {
      const ang = c.length === 2 ? (j === 0 ? Math.PI : 0) : (2 * Math.PI * j) / c.length - Math.PI / 2
      pos[id] = { x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) * (c.length === 2 ? 1 : 0.85) }
    })
  })
  return pos
}

function Graph({ data, all, onEdge, height }: { data: any; all: boolean; onEdge: (e: any) => void; height?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const nav = useNavigate()
  useEffect(() => {
    if (!ref.current || !data) return
    const nodes = data.nodes.filter((n: any) => all || n.linked)
    const ids = new Set(nodes.map((n: any) => n.id))
    const layout = { name: 'preset', positions: arrange(nodes, data.edges), padding: 70 } as any
    const cy = cytoscape({
      container: ref.current, wheelSensitivity: 0.25, minZoom: 0.3, maxZoom: 2.5,
      elements: [
        ...nodes.map((n: any) => ({ data: { id: n.id, label: short(n.label), lane: n.lane, app: n.application_id } })),
        ...data.edges.filter((e: any) => ids.has(e.source) && ids.has(e.target)).map((e: any) => ({
          data: { id: 'e' + data.edges.indexOf(e), source: e.source, target: e.target, w: e.weight, sev: e.severity, label: edgeLabel(e), idx: data.edges.indexOf(e) } })),
      ],
      style: [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 13, color: '#222', 'text-valign': 'bottom', 'text-margin-y': 7, 'text-wrap': 'wrap',
          'text-max-width': '150px', width: 34, height: 34, 'background-color': '#999', 'border-width': 3, 'border-color': '#fff' } },
        ...Object.entries(LANE_COLOR).map(([l, c]) => ({ selector: `node[lane="${l}"]`, style: { 'background-color': c } })),
        { selector: 'edge', style: { width: 'mapData(w, 1, 8, 3, 9)', 'line-color': '#7a6a9a', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 12,
          color: '#4a3d63', 'text-background-color': '#fff', 'text-background-opacity': 1, 'text-background-padding': '3px', 'text-rotation': 'autorotate' } },
        { selector: 'edge[sev="critical"]', style: { 'line-color': '#b23a2e', color: '#8e2c22' } },
        { selector: '.faded', style: { opacity: 0.15 } },
        { selector: 'node:selected', style: { 'border-color': '#c8691c', 'border-width': 4 } },
      ] as any,
      layout,
    })
    cy.on('mouseover', 'node', (e) => { cy.elements().not(e.target.closedNeighborhood()).addClass('faded') })
    cy.on('mouseout', 'node', () => cy.elements().removeClass('faded'))
    cy.on('tap', 'edge', (e) => onEdge(data.edges[e.target.data('idx')]))
    cy.on('dbltap', 'node', (e) => nav(`/app/${e.target.data('app')}`))
    cy.on('tap', 'node', (e) => { const es = e.target.connectedEdges(); if (es.length === 1) onEdge(data.edges[es[0].data('idx')]) })
    cyRef.current = cy
    return () => cy.destroy()
  }, [data, all])
  const z = (f: number) => { const cy = cyRef.current; if (cy) cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }
  return (
    <div className="graphwrap">
      <div className="graphtools">
        <button className="btn" title="Zoom in" onClick={() => z(1.25)}>+</button>
        <button className="btn" title="Zoom out" onClick={() => z(0.8)}>−</button>
        <button className="btn" title="Fit to screen" onClick={() => cyRef.current?.fit(undefined, 50)}>⤢</button>
        <button className="btn" title="Re-arrange" onClick={() => cyRef.current?.layout({ name: 'cose', animate: true, randomize: true, nodeRepulsion: () => 140000,
          idealEdgeLength: () => 210, padding: 60, nodeDimensionsIncludeLabels: true } as any).run()}>↻</button>
      </div>
      <div ref={ref} className="graph" style={height ? { height } : undefined} />
    </div>
  )
}

export default function Network() {
  const [g, setG] = useState<any>(null)
  const [all, setAll] = useState(false)
  const [edge, setEdge] = useState<any>(null)
  const [big, setBig] = useState(false)
  useEffect(() => { api('/api/network').then(setG) }, [])
  const node = (pid: string) => g?.nodes.find((n: any) => n.id === pid)
  const name = (pid: string) => titleCase(node(pid)?.label || pid)
  return (
    <div>
      <div className="titlebar">
        <div><h1>Links between institutions <Tip>The same person, photo or certificate number should belong to one institution only. A line means two institutions share one. It is a lead to verify, not a conclusion: a shared teacher may simply have moved jobs.</Tip></h1>
          <div className="sub">{g?.edges.length || 0} pairs of institutions share something</div></div>
        <div className="row">
          <label className="row small"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show all institutions</label>
          <button className="btn" onClick={() => setBig(true)}>⤢ Enlarge</button>
        </div>
      </div>
      <div className="box" style={{ marginBottom: 14 }}>
        <div className="bh"><div className="legend">
          <span><b style={{ background: LANE_COLOR.red }} />Alert</span><span><b style={{ background: LANE_COLOR.amber }} />Needs action</span>
          <span><b style={{ background: LANE_COLOR.green }} />Clear</span>
          <span><i style={{ background: '#b23a2e' }} />shared certificate</span><span><i style={{ background: '#7a6a9a' }} />shared faculty or photo</span>
        </div><span className="small faint">Drag to move · scroll to zoom · click a line for details · double-click a college to open it</span></div>
        {g && <Graph data={g} all={all} onEdge={setEdge} />}
      </div>
      <div className="box">
        <div className="bh"><h3>All links</h3></div>
        <div className="tablewrap"><table className="t">
          <thead><tr><th>Institution</th><th>Institution</th><th>What is shared</th><th /></tr></thead>
          <tbody>{g?.edges.map((e: any, i: number) => <tr key={i} className="click" onClick={() => setEdge(e)}>
            <td>{name(e.source)}<div><Lane lane={node(e.source)?.lane} /></div></td>
            <td>{name(e.target)}<div><Lane lane={node(e.target)?.lane} /></div></td>
            <td>{edgeLabel(e)}</td><td><button className="btn sm">Details</button></td></tr>)}</tbody>
        </table></div>
      </div>
      {big && g && <Modal full title="Links between institutions" onClose={() => setBig(false)}>
        <Graph data={g} all={all} onEdge={(e) => { setBig(false); setEdge(e) }} height="calc(94vh - 90px)" />
      </Modal>}
      {edge && <Modal title={`${name(edge.source)} ↔ ${name(edge.target)}`} onClose={() => setEdge(null)}>
        {edge.items.map((it: any, i: number) => (
          <div key={i} className="box" style={{ marginBottom: 10 }}>
            <div className="bh"><h3>{KIND[it.type] || it.label}</h3>{it.type === 'photo' && <span className="small faint">matched despite cropping/resizing</span>}</div>
            <div className="tablewrap"><table className="t small"><tbody>{it.members.map((m: any, j: number) => <tr key={j}>
              <td style={{ width: '38%' }}><Link to={`/app/${m.application_id}`}>{name(m.permanent_id)}</Link></td>
              <td>{m.document_id ? <Link to={`/app/${m.application_id}/doc/${m.document_id}`}>{m.display}</Link> : m.display}
                {m.extra?.dob && <div className="faint">Born {m.extra.dob}{m.extra.joined ? ` · joined ${m.extra.joined}` : ''}</div>}</td></tr>)}</tbody></table></div>
            {it.type === 'photo' && <div className="grid g2" style={{ padding: 10 }}>{it.members.map((m: any) =>
              <img key={m.document_id} alt="photo" style={{ width: '100%' }} src={img(`/api/documents/${m.document_id}/page/0.png`)} />)}</div>}
          </div>
        ))}
      </Modal>}
    </div>
  )
}

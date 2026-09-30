import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ConfigView } from '../src/views/ConfigView'
import { ChatView } from '../src/views/ChatView'
import { HistoryView } from '../src/views/HistoryView'
import type { SceneMode } from '../src/api/client'

const date = '2026-09-29T00:00:00Z'
const templates = ['甲','乙','丙'].map((name,i) => ({ template_id:`tpl-${i}`,name,persona:`PRIVATE_${i}`,speech_style:'',initial_goal:'',private_background:'',public_profile:`PUBLIC_${i}`,created_at:date,updated_at:date }))
const agents = templates.map((t,i) => ({agent_id:`agt-${i}`,scene_id:'scn-dm',name:t.name,order_index:i,created_at:date,snapshot:{...t,source_template_id:t.template_id,captured_at:date},discussion_config:{focus:`FOCUS_${i}`,initial_position:null}}))
const state = { scene_id:'scn-dm',status:'PAUSED',pause_reason:'MANUAL',role_requests_used:2,max_role_requests:5,analysis_requests_used:0,max_analysis_requests:4,last_committed_seq:1,in_flight:false }
const privateEntry = {kind:'message',seq:1,author_name:'甲',message:{message_id:'hidden-id',scene_id:'scn-dm',seq:1,actor_id:'agt-0',recipient_id:'agt-1',conversation_id:'hidden-pair',visibility:'PRIVATE',text:'HIDDEN_PRIVATE',created_at:date,schema_version:2}}
function response(value:unknown,status=200):Response { return {ok:status<400,status,json:async()=>value} as Response }
function detail(mode:SceneMode) { return {scene:{scene_id:'scn-dm',title:`${mode} 场景`,mode,mode_config:mode==='discussion'?{topic:'讨论题',materials:'公共资料'}:{situation:'模拟场景',public_information:''},background:mode==='discussion'?'讨论题\n公共资料':'模拟场景',status:'PAUSED',budget:{max_role_requests:5,max_analysis_requests:4},created_at:date},agents,locked:true} }
function install(mode:SceneMode) {
  const fetchMock=vi.fn(async (input:RequestInfo|URL,init?:RequestInit) => {
    const url=new URL(String(input),'http://localhost');const path=url.pathname;const third=url.searchParams.get('viewer_id')==='agt-2'
    if(path==='/api/templates') return response({templates})
    if(path==='/api/scenes/presets') return response({presets:[]})
    if(path==='/api/scenes') {
      if(init?.method==='POST') return response(detail(mode),201)
      const all=[{scene_id:'scn-dm',title:'讨论记录',mode:'discussion'},{scene_id:'scn-sim',title:'模拟记录',mode:'simulation'}]
      return response({scenes:all.filter(s=>!url.searchParams.get('mode')||s.mode===url.searchParams.get('mode'))})
    }
    if(path==='/api/scenes/scn-dm') return response(detail(mode))
    if(path.endsWith('/state')) return response(state)
    if(path.endsWith('/summary')) return response({succeeded:2,failed:0,unknown:0,max_role_requests:5})
    if(path.endsWith('/events')) return response([])
    if(path.endsWith('/agents/status')) return response({agents:[]})
    if(path.endsWith('/timeline')) return response({entries:third?[]:[privateEntry],conversations:third?[]:[{conversation_id:'hidden-pair',participant_names:['甲','乙'],participant_ids:['agt-0','agt-1'],message_count:1}],actions:[]})
    if(path.endsWith('/statistics')) return response({scene_id:'scn-dm',viewer_id:third?'agt-2':null,public_messages:0,private_messages:third?0:1,participant_ids:third?[]:['agt-0','agt-1'],reply_relations:[],role_actions:[]})
    if(path.endsWith('/viewpoint')) return response({prompt:'本人合法输入',prompt_template_id:`role_action@${mode}.p1.1`,public_roster:['甲','乙','丙'],cutoff_seq:0,visible_seq:[],visible_kinds:[]})
    return response({detail:path},404)
  })
  vi.stubGlobal('fetch',fetchMock)
  vi.stubGlobal('EventSource',class { addEventListener(){} removeEventListener(){} close(){} })
  return fetchMock
}
beforeEach(()=>sessionStorage.clear())
afterEach(()=>vi.unstubAllGlobals())

it.each<SceneMode>(['simulation','discussion'])('两入口使用 %s 合法表单，提交正确配置且创建零角色调用',async mode=>{
  const fetchMock=install(mode); const user=userEvent.setup();const open=vi.fn()
  render(<ConfigView onOpenScene={open} />)
  expect(await screen.findByText('想观察什么？')).toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:mode==='discussion'?/议题聊天室/:/角色互动沙盒/}))
  if(mode==='discussion') {
    expect(screen.queryByLabelText('场景背景')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button',{name:'创建会话'}))
    expect(await screen.findByText('议题不能为空')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(c=>c[1]?.method==='POST')).toHaveLength(0)
    await user.type(screen.getByLabelText('议题'),'不预设立场的议题')
  }
  const choices=screen.getAllByRole('checkbox');await user.click(choices[0]!);await user.click(choices[1]!)
  if(mode==='discussion') {
    expect(screen.getByLabelText('甲的初始观点')).toHaveValue('')
    expect(screen.getAllByText(/仅 甲 本人可见/)).toHaveLength(2)
    await user.type(screen.getByLabelText('甲的讨论关注点'),'本人关注')
  }
  await user.click(screen.getByRole('button',{name:'创建会话'}))
  await waitFor(()=>expect(open).toHaveBeenCalledWith('scn-dm'))
  const post=fetchMock.mock.calls.find(c=>c[1]?.method==='POST')!
  const body=JSON.parse(String(post[1]?.body))
  expect(body.mode).toBe(mode)
  expect(body.agents).toHaveLength(2)
  if(mode==='discussion') {expect(body.agents[0].discussion_config.focus).toBe('本人关注');expect(body.agents[0].discussion_config.initial_position??null).toBeNull();expect(body.mode_config.situation).toBeUndefined()}
  else {expect(body.agents[0].discussion_config).toBeUndefined();expect(body.mode_config.topic).toBeUndefined()}
  expect(fetchMock.mock.calls.some(c=>String(c[0]).includes('/commands'))).toBe(false)
})

it.each<SceneMode>(['simulation','discussion'])('共用 ChatView 展示 %s 信息，第三方无隐藏资料/统计缓存',async mode=>{
  const fetchMock=install(mode);const user=userEvent.setup()
  render(<ChatView sceneId="scn-dm" readOnly modelConfigured={false} onSelectScene={()=>undefined} />)
  expect(await screen.findByText('HIDDEN_PRIVATE')).toBeInTheDocument()
  expect(await screen.findByRole('region',{name:'记录事实'})).toHaveTextContent('私聊消息 1')
  expect(screen.getByText(mode==='discussion'?'议题与材料':'情境与公共信息')).toBeInTheDocument()
  expect(screen.getAllByText(/PUBLIC_0/).length).toBeGreaterThan(0)
  await user.click(screen.getByRole('button',{name:/^丙/}))
  expect(screen.queryByText('HIDDEN_PRIVATE')).not.toBeInTheDocument()
  expect(screen.queryByText('人物设定：PRIVATE_0')).not.toBeInTheDocument()
  await waitFor(()=>expect(screen.getByRole('region',{name:'记录事实'})).toHaveTextContent('私聊消息 0'))
  expect(screen.queryByText('甲 ↔ 乙')).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.every(c=>!c[1]?.method||c[1]?.method==='GET')).toBe(true)
})

it('历史全部/两模式筛选和刷新共用列表，零创建/派发，保存筛选',async()=>{
  const fetchMock=install('discussion');const user=userEvent.setup()
  render(<HistoryView sceneId={null} modelConfigured={false} onSelectScene={()=>undefined} />)
  expect(await screen.findByText(/讨论记录/)).toBeInTheDocument()
  expect(screen.getByText(/模拟记录/)).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('历史模式筛选'),'discussion')
  expect(await screen.findByText(/讨论记录/)).toBeInTheDocument()
  expect(screen.queryByText(/模拟记录/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'刷新历史'}))
  await user.selectOptions(screen.getByLabelText('历史模式筛选'),'simulation')
  expect(await screen.findByText(/模拟记录/)).toBeInTheDocument()
  expect(screen.queryByText(/讨论记录/)).not.toBeInTheDocument()
  expect(sessionStorage.getItem('sceneweave:history-mode')).toBe('"simulation"')
  expect(fetchMock.mock.calls.some(c=>String(c[0]).includes('?mode=discussion'))).toBe(true)
  expect(fetchMock.mock.calls.every(c=>!c[1]?.method||c[1]?.method==='GET')).toBe(true)
  expect(screen.queryByRole('button',{name:'用预置场景创建会话'})).not.toBeInTheDocument()
})

it('刷新恢复保存的角色/频道仅请求本人集合，存储不含正文或私人配置',async()=>{
  sessionStorage.setItem('sceneweave:viewer:scn-dm','"agt-2"')
  sessionStorage.setItem('sceneweave:channel:scn-dm:agt-2','"public"')
  const fetchMock=install('discussion')
  render(<ChatView sceneId="scn-dm" readOnly modelConfigured={false} onSelectScene={()=>undefined} />)
  expect(await screen.findByText('本人合法输入')).toBeInTheDocument()
  expect(screen.queryByText('HIDDEN_PRIVATE')).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.some(c=>String(c[0]).includes('timeline?viewer_id=agt-2'))).toBe(true)
  expect(JSON.stringify(sessionStorage)).not.toContain('PRIVATE_')
})

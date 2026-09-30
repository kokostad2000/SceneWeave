import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfigView } from '../src/views/ConfigView'
import { ChatView } from '../src/views/ChatView'

function response(value: unknown, status=200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type':'application/json' } }) }
function install(version=2,locked=false) {
  const identities=['甲','乙'].map((name,i)=>({name,template_id:`tpl-${i}`,persona:'旧露营人设',speech_style:'旧表达',initial_goal:'旧营地目标',private_background:'旧背景',public_profile:'旧公开身份'}))
  const detail={scene:{scene_id:'scn-sr',title:'新讨论',mode:'discussion',configuration_version:version,status:'READY',background:'议题',mode_config:{topic:'议题',materials:''}},locked,
    agents:identities.map((t,i)=>({agent_id:`agt-${i}`,name:t.name,order_index:i,snapshot:{...t,name:t.name,persona:'',speech_style:'',initial_goal:'',private_background:'',public_profile:''},discussion_config:{focus:'',initial_position:null}}))}
  const fetchMock=vi.fn(async(input: RequestInfo|URL,init?:RequestInit)=>{
    const path=String(input);const method=init?.method??'GET'
    if(path==='/api/templates') {
      if(method==='POST') return response({...identities[0],...JSON.parse(String(init?.body)),template_id:'tpl-new'},201)
      return response({templates:identities})
    }
    if(path==='/api/scenes/presets') return response({presets:[{key:'campsite',title:'露营预设',background:'营地',agent_names:['甲','乙']}]})
    if(path==='/api/scenes/preset') return response(detail,201)
    if(path==='/api/scenes') return method==='POST'?response(detail,201):response({scenes:[]})
    if(path.endsWith('/profile')) {
      if(detail.locked) return response({detail:'场景已开始，不能修改本场设定'},409)
      const body=JSON.parse(String(init?.body));Object.assign(detail.agents[0]!.snapshot,body.role_profile)
      if(body.discussion_config) detail.agents[0]!.discussion_config=body.discussion_config
      return response(detail.agents[0])
    }
    if(path==='/api/scenes/scn-sr') return response(detail)
    if(path.endsWith('/state')) return response({scene_id:'scn-sr',status:'READY',in_flight:false,role_requests_used:0,max_role_requests:200,analysis_requests_used:0,max_analysis_requests:4})
    if(path.endsWith('/events')) return response([])
    if(path.endsWith('/summary')) return response({succeeded:0,failed:0,unknown:0,max_role_requests:200})
    if(path.endsWith('/timeline')) return response({entries:[],actions:[],conversations:[]})
    if(path.endsWith('/agents/status')) return response({agents:[]})
    if(path.endsWith('/statistics')) return response({public_messages:0,private_messages:0,participant_ids:[],reply_relations:[],role_actions:[]})
    return response({detail:path},404)
  })
  vi.stubGlobal('fetch',fetchMock)
  vi.stubGlobal('EventSource',class{addEventListener(){} removeEventListener(){} close(){}})
  return {fetchMock,detail}
}
beforeEach(()=>sessionStorage.clear())
afterEach(()=>vi.unstubAllGlobals())

it.each(['simulation','discussion'])('新版 %s 创建的本场资料不继承旧人物设定',async mode=>{
  const {fetchMock}=install();const user=userEvent.setup();render(<ConfigView onOpenScene={()=>undefined}/>)
  await screen.findByText('人物目录')
  if(mode==='discussion') {await user.click(screen.getByRole('button',{name:/议题聊天室/}));await user.type(screen.getByLabelText('议题'),'新议题')}
  const choices=screen.getAllByRole('checkbox');await user.click(choices[0]!);await user.click(choices[1]!)
  expect(screen.getByLabelText('甲的本场初始目标')).toHaveValue('')
  expect(screen.getByLabelText('甲的本场公开身份／自我介绍')).toHaveValue('')
  expect(screen.queryByText('旧露营人设')).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('甲的本场人物设定'),'本场个性')
  await user.click(screen.getByRole('button',{name:'创建会话'}))
  await waitFor(()=>expect(fetchMock.mock.calls.some(c=>String(c[0])==='/api/scenes'&&c[1]?.method==='POST')).toBe(true))
  const call=fetchMock.mock.calls.find(c=>String(c[0])==='/api/scenes'&&c[1]?.method==='POST')!
  const body=JSON.parse(String(call[1]?.body));expect(body.configuration_version).toBe(2);expect(body.chat_policy_version).toBe(2)
  expect(body.agents[0].role_profile).toEqual({public_profile:'',persona:'本场个性',speech_style:'',initial_goal:'',private_background:''})
  expect(body.agents[1].role_profile.persona).toBe('')
  expect(fetchMock.mock.calls.some(c=>String(c[0]).includes('/commands'))).toBe(false)
})

it('人物目录仅提交名称',async()=>{
  const {fetchMock}=install();const user=userEvent.setup();render(<ConfigView onOpenScene={()=>undefined}/>)
  await screen.findByText('人物目录');expect(screen.queryByLabelText('人物设定')).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('名称'),'新人物');await user.click(screen.getByRole('button',{name:'创建人物'}))
  const call=fetchMock.mock.calls.find(c=>String(c[0])==='/api/templates'&&c[1]?.method==='POST')!
  expect(JSON.parse(String(call[1]?.body))).toEqual({name:'新人物'})
})

it('预置场景显式提交新版配置',async()=>{
  const {fetchMock}=install();const user=userEvent.setup();render(<ConfigView onOpenScene={()=>undefined}/>)
  await user.click(await screen.findByRole('button',{name:'用预置场景创建会话'}))
  const call=fetchMock.mock.calls.find(c=>String(c[0])==='/api/scenes/preset')!
  expect(JSON.parse(String(call[1]?.body))).toEqual({preset_key:'campsite',configuration_version:2,chat_policy_version:2})
})

it('开始前编辑只提交本场配置，保存后显示新快照且零角色调用',async()=>{
  const {fetchMock}=install();const user=userEvent.setup();render(<ChatView sceneId="scn-sr" modelConfigured={false} onSelectScene={()=>undefined}/>)
  await user.click(await screen.findByRole('button',{name:'编辑甲的本场设定'}))
  await user.type(screen.getByLabelText('甲的本场私有背景'),'本场信息')
  await user.click(screen.getByRole('button',{name:'保存本场设定'}))
  expect(await screen.findByText('私有背景：本场信息')).toBeInTheDocument()
  const calls=fetchMock.mock.calls.filter(c=>c[1]?.method==='PATCH')
  expect(calls).toHaveLength(1);expect(String(calls[0]![0])).toBe('/api/scenes/scn-sr/agents/agt-0/profile')
  expect(fetchMock.mock.calls.some(c=>String(c[0]).includes('/commands'))).toBe(false)
})

it.each([{version:1,locked:false,readOnly:false},{version:2,locked:true,readOnly:false},{version:2,locked:false,readOnly:true}])('旧版、已锁定或历史页不允许修改本场设定：%j',async c=>{
  const {fetchMock}=install(c.version,c.locked);render(<ChatView sceneId="scn-sr" readOnly={c.readOnly} modelConfigured={false} onSelectScene={()=>undefined}/>)
  await screen.findByText('本场角色（快照）')
  expect(screen.queryByRole('button',{name:'编辑甲的本场设定'})).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.every(c=>!c[1]?.method||c[1]?.method==='GET')).toBe(true)
})

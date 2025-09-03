import useSWR from 'swr'; import axios from 'axios'; import Header from '../components/Header'
const fetcher = url => axios.get(url).then(r=>r.data)
export default function Home(){ const api = '/api/products'; const { data, error } = useSWR(api, fetcher)
  if(error) return <div>Error loading</div>; if(!data) return <div>Loading...</div>
  return (<div><Header /><main className="container py-6"><h1 className="text-3xl font-bold mb-6">Products</h1><div className="grid grid-cols-1 sm:grid-cols-2 gap-6">{data.map(p=> (<div key={p.id} className="border rounded p-4"><img src={p.image_url||'/placeholder.png'} className="h-40 w-full object-cover mb-2"/><h2 className="text-xl font-semibold">{p.title}</h2><p className="mt-2">${p.price}</p><a className="text-blue-600" href={'/product/'+p.id}>View</a></div>))}</div></main></div>) }

import Link from 'next/link'
export default function Header({ user }){
  return (
    <header className="bg-white shadow">
      <div className="container flex items-center justify-between py-4">
        <Link href='/'><a className="text-xl font-bold">Ruke Store</a></Link>
        <nav>
          <Link href='/'><a className="mr-4">Home</a></Link>
          <Link href='/cart'><a className="mr-4">Cart</a></Link>
          <Link href='/auth/login'><a>Login</a></Link>
        </nav>
      </div>
    </header>
  )
}

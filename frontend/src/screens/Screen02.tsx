import React, { useState } from 'react';
import { useAppRouter, Button, Input, AuthContainer } from '../components/shared';

const Screen02Login = () => {
  const { navigate, setUser } = useAppRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const normalized = email.trim().toLowerCase();
    if (!normalized || !password) { setError('Enter your email and password.'); return; }

    // Frontend demo auth only. The backend must replace this with real authentication.
    const isAdmin = normalized === 'admin@oauife.edu.ng' || normalized.startsWith('admin@');
    const role = isAdmin ? 'admin' : normalized.includes('faculty') ? 'faculty' : normalized.includes('research') ? 'researcher' : 'student';
    const name = isAdmin ? 'OAU Thesis Bank Admin' : normalized.split('@')[0].replace(/[._-]/g, ' ');

    setUser({ id: `demo-${role}`, name, email: normalized, role });
    navigate(isAdmin ? 'admin-dashboard' : 'discover');
  };

  return (
    <AuthContainer title="Sign in to your account" subtitle="Use your OAU institutional email">
      <form className="space-y-6" onSubmit={submit}>
        <Input label="OAU Email address" type="email" placeholder="student@student.oauife.edu.ng" value={email} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} />
        <Input label="Password" type="password" placeholder="••••••••" value={password} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex items-center justify-between">
          <label className="flex items-center text-sm text-slate-700"><input type="checkbox" className="h-4 w-4 text-[#00502F] focus:ring-[#00502F] border-slate-300 rounded" /> <span className="ml-2">Remember me</span></label>
          <button type="button" onClick={() => navigate('password-reset')} className="text-sm font-medium text-[#00502F] hover:text-[#003d24]">Forgot password?</button>
        </div>
        <Button type="submit" className="w-full">Sign in</Button>
      </form>
      <div className="mt-6 text-center text-sm"><span className="text-slate-600">Don't have an account? </span><button onClick={() => navigate('signup')} className="font-medium text-[#00502F] hover:text-[#003d24]">Sign up</button></div>
      <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><strong>Frontend demo:</strong> use <code>admin@oauife.edu.ng</code> to preview the admin portal. Any other email previews the researcher workspace. This is not real authentication yet.</div>
    </AuthContainer>
  );
};
export default Screen02Login;

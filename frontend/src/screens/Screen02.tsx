import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen02Login = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthContainer title="Sign in to your account" subtitle="Use your OAU institutional email">
      <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); navigate('discover'); }}>
        <Input label="OAU Email address" type="email" placeholder="student@student.oauife.edu.ng" />
        <Input label="Password" type="password" placeholder="••••••••" />
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <input id="remember-me" type="checkbox" className="h-4 w-4 text-[#00502F] focus:ring-[#00502F] border-slate-300 rounded" />
            <label htmlFor="remember-me" className="ml-2 block text-sm text-slate-900">Remember me</label>
          </div>
          <div className="text-sm">
            <button type="button" onClick={() => navigate('password-reset')} className="font-medium text-[#00502F] hover:text-[#003d24]">Forgot password?</button>
          </div>
        </div>
        <Button type="submit" className="w-full">Sign in</Button>
      </form>
      <div className="mt-6 text-center text-sm">
        <span className="text-slate-600">Don't have an account? </span>
        <button onClick={() => navigate('signup')} className="font-medium text-[#00502F] hover:text-[#003d24]">Sign up</button>
      </div>
    </AuthContainer>
  );
};

export default Screen02Login;

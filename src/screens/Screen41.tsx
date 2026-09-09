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

const Screen41AccountSettings = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Account Settings">
      <div className="max-w-4xl mx-auto flex flex-col md:flex-row gap-8">
        <div className="w-full md:w-64 flex-shrink-0">
          <nav className="space-y-1">
            <button className="w-full flex items-center px-3 py-2 bg-emerald-50 text-[#00502F] font-medium rounded-md text-sm"><User className="w-4 h-4 mr-3"/> Profile Info</button>
            <button className="w-full flex items-center px-3 py-2 text-slate-600 hover:bg-slate-50 font-medium rounded-md text-sm" onClick={() => navigate('privacy-settings')}><Shield className="w-4 h-4 mr-3"/> Privacy & Access</button>
          </nav>
        </div>
        
        <div className="flex-1 space-y-6">
          <Card className="p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Public Profile</h3>
            <div className="flex items-center space-x-6 mb-6">
              <div className="w-20 h-20 bg-[#00502F] rounded-full text-white flex items-center justify-center text-2xl font-bold">AO</div>
              <Button variant="secondary" size="sm">Change Avatar</Button>
            </div>
            <form className="space-y-4 max-w-lg">
              <Input label="Full Name" value="Adekunle Ojo" onChange={()=>{}}/>
              <Input label="Department" value="Agricultural Engineering" disabled onChange={()=>{}}/>
              <div className="flex flex-col space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Bio</label>
                <textarea className="px-3 py-2 border border-slate-300 rounded-md h-24 text-sm resize-none" defaultValue="Passionate about leveraging machine learning..." />
              </div>
              <Button>Save Profile</Button>
            </form>
          </Card>

          <Card className="p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Connected Accounts</h3>
            <div className="space-y-4 max-w-lg">
              <div className="flex justify-between items-center p-3 border border-slate-200 rounded">
                <span className="text-sm font-medium flex items-center"><LinkIcon className="w-4 h-4 mr-2 text-slate-400"/> GitHub</span>
                <Button variant="ghost" size="sm">Connect</Button>
              </div>
              <div className="flex justify-between items-center p-3 border border-slate-200 rounded">
                <span className="text-sm font-medium flex items-center"><LinkIcon className="w-4 h-4 mr-2 text-[#00502F]"/> ORCID (0000-0002-...)</span>
                <Button variant="ghost" size="sm" className="text-red-500">Disconnect</Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen41AccountSettings;

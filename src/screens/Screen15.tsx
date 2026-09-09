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

const Screen15ThesisMetadata = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Thesis Details">
      <div className="max-w-3xl mx-auto">
        <UploadWizardNav step={2} />
        <Card className="p-8">
          <h2 className="text-xl font-bold text-slate-900 mb-6">Confirm Metadata</h2>
          <p className="text-sm text-slate-500 mb-6 flex items-center"><Cpu className="w-4 h-4 mr-2 text-emerald-600"/> We've auto-extracted some details from your document.</p>
          
          <form className="space-y-6">
            <Input label="Research Title" value="Machine Learning for Crop Yield Prediction in Nigeria" onChange={()=>{}} />
            
            <div className="grid grid-cols-2 gap-6">
              <Input label="Author" value="Adekunle Ojo" onChange={()=>{}} />
              <Input label="Year" value="2023" onChange={()=>{}} />
              <div className="flex flex-col space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Department</label>
                <select className="px-3 py-2 border border-slate-300 rounded-md bg-white text-slate-900">
                  <option>Agricultural Engineering</option>
                  <option>Computer Science</option>
                </select>
              </div>
              <Input label="Supervisor" value="Dr. O. A. Fajemisin" onChange={()=>{}} />
            </div>

            <div className="flex flex-col space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Abstract</label>
              <textarea className="px-3 py-2 border border-slate-300 rounded-md h-32 resize-none text-sm" value="This study applies random forest regressors to predict crop yields..." readOnly></textarea>
            </div>

            <Input label="Keywords (comma separated)" value="Machine Learning, Agriculture, Predictive Modeling" onChange={()=>{}} />

            <div className="pt-6 border-t border-slate-200 flex justify-between">
              <Button variant="ghost" onClick={() => navigate('upload')}>Back</Button>
              <Button onClick={() => navigate('access-privacy')}>Continue to Privacy</Button>
            </div>
          </form>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen15ThesisMetadata;
